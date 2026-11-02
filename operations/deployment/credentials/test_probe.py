"""Synthetic service accounts and a local invented TLS server only."""
import contextlib
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import io
import json
from pathlib import Path
import shutil
import ssl
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

import probe

TOKENS = {name:chr(65+i)*43 for i,name in enumerate(probe.NAMES)}
NOW = datetime(2026,11,2,tzinfo=timezone.utc)


def whoami(name):
    return {'youare':{'attrs':{'name':[name], 'uuid':['11111111-2222-4333-8444-555555555555'],
        'class':['object','account','service_account'],
        'memberof':['idm_people_on_boarding@log.mrj.am','idm_account_mail_read@log.mrj.am']}}}


class Probe(unittest.TestCase):
    def test_only_fixed_service_identities_and_boolean_results_are_returned(self):
        calls=[]
        def get(token,path):
            calls.append((token,path))
            if path == '/v1/self':
                role=next(n for n,v in TOKENS.items() if v==token)
                return whoami(probe.ACCOUNTS[role])
            return None
        result=probe.examine(TOKENS,get,NOW)
        self.assertTrue(result['all_tokens_present'])
        self.assertTrue(result['tokens_distinct'])
        self.assertFalse(result['administrative_prestate_observable'])
        self.assertFalse(result['write_authorization_proved'])
        self.assertEqual(len(calls),21)
        self.assertTrue(all(path in probe.PATHS for _,path in calls))
        encoded=json.dumps(result)
        for token in TOKENS.values(): self.assertNotIn(token,encoded)
        self.assertNotIn('11111111',encoded)
        self.assertNotIn('memberof',encoded)
        self.assertTrue(all(type(v) is bool for k,v in result.items() if k not in (*probe.NAMES,'schema_version')))
        self.assertTrue(all(type(v) is bool for n in probe.NAMES for v in result[n].values()))

    def test_missing_or_reused_tokens_do_not_imply_three_capabilities(self):
        for values in ({n:None for n in probe.NAMES}, {n:'A'*43 for n in probe.NAMES}):
            result=probe.examine(values,lambda token,path:None,NOW)
            self.assertFalse(result['tokens_distinct'])
            self.assertFalse(any(result[n]['authenticated_service'] for n in probe.NAMES))

    def test_a_person_or_another_service_is_not_the_expected_service(self):
        value=whoami('mrjam-admission')
        self.assertIsNotNone(probe.identity(value,'mrjam-admission'))
        for field,replacement in [('name',['mrjam-cycle']), ('class',['person','account']),
                                   ('class','service_account'), ('uuid',['not-a-uuid']),
                                   ('uuid',[]), ('name',['mrjam-admission','other'])]:
            bad=whoami('mrjam-admission');bad['youare']['attrs'][field]=replacement
            self.assertIsNone(probe.identity(bad,'mrjam-admission'))

    def test_unknown_null_or_future_admin_state_is_not_provisioning_authority(self):
        for state,expected_observable,expected_disabled in [(None,False,False),([],False,False),
                    (['2099-01-01T00:00:00Z'],True,False),(['2026-01-01T00:00:00Z'],True,True)]:
            def get(token,path):
                if path=='/v1/self':return whoami('mrjam-admission')
                return state if path.endswith('account_expire') else []
            result=probe.examine({'admission':TOKENS['admission'],'cycle':None,'replay':None},get,NOW)
            self.assertEqual(result['administrative_prestate_observable'],expected_observable)
            self.assertEqual(result['builtin_admins_disabled'],expected_disabled)
        def hidden(token,path):
            if path=='/v1/self':return whoami('mrjam-admission')
            return ['2026-01-01T00:00:00Z'] if path.endswith('account_expire') else None
        self.assertFalse(probe.examine({'admission':TOKENS['admission']},hidden,NOW)['administrative_prestate_observable'])

    def test_unknown_json_duplicate_and_unbounded_paths_are_refused(self):
        with self.assertRaises(probe.Refused):probe.parse_json(b'{"x":1,"x":2}')
        for path in ('/v1/person','/v1/service_account','/v1/self/_uat','https://elsewhere.invalid'):
            with self.assertRaises(probe.Refused):probe.request('A'*43,path,None)
        with self.assertRaises(probe.Refused):probe.request('bad\r\nHeader: x','/v1/self',None)

    def test_exact_ca_hash_is_required(self):
        with self.assertRaises(probe.Refused):probe.tls_context(b'INVENTED_CA_BYTES','0'*64)

    def test_real_tls_requires_ca_and_name_and_sends_only_get(self):
        openssl=shutil.which('openssl')
        self.assertIsNotNone(openssl,'OpenSSL required for an actual TLS fixture')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            def certificate(name,stem):
                key=root/(stem+'.key');cert=root/(stem+'.pem')
                subprocess.run([openssl,'req','-x509','-newkey','rsa:2048','-nodes','-days','1',
                    '-subj','/CN='+name,'-addext','subjectAltName=DNS:'+name,
                    '-keyout',str(key),'-out',str(cert)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                key.chmod(0o600)
                return key,cert
            key,cert=certificate('log.mrj.am','correct')
            wrong_key,wrong_cert=certificate('wrong.example.invalid','wrong')
            for actual_key,actual_cert,client_ca,success in ((key,cert,cert,True),(wrong_key,wrong_cert,wrong_cert,False),(key,cert,wrong_cert,False)):
                calls=[]
                class Handler(BaseHTTPRequestHandler):
                    def do_GET(self):
                        calls.append((self.command,self.path,self.headers.get('Host'),self.headers.get('Authorization')))
                        body=json.dumps(whoami('mrjam-admission')).encode()
                        self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)))
                        self.end_headers();self.wfile.write(body)
                    def log_message(self,*args):pass
                server=HTTPServer(('127.0.0.1',0),Handler)
                tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);tls.load_cert_chain(actual_cert,actual_key)
                server.socket=tls.wrap_socket(server.socket,server_side=True)
                thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
                try:
                    ca=client_ca.read_bytes();ctx=probe.tls_context(ca,hashlib.sha256(ca).hexdigest())
                    if success:
                        value=probe.request('A'*43,'/v1/self',ctx,port=server.server_port)
                        self.assertIsNotNone(probe.identity(value,'mrjam-admission'))
                        self.assertEqual(calls,[('GET','/v1/self','log.mrj.am','Bearer '+'A'*43)])
                    else:
                        with self.assertRaises(ssl.SSLError):probe.request('A'*43,'/v1/self',ctx,port=server.server_port)
                        self.assertEqual(calls,[])
                finally:
                    server.shutdown();server.server_close();thread.join(timeout=2)

    def test_cli_refusals_never_emit_secret_values_or_exception_details(self):
        for argv,uid in [(['probe','arbitrary'],0),(['probe'],59990),(['probe'],0)]:
            out,err=io.StringIO(),io.StringIO()
            with patch.object(probe.sys,'argv',argv),patch.object(probe.os,'geteuid',return_value=uid), \
                    patch.object(probe.Path,'read_bytes',side_effect=ValueError('INVENTED_PRIVATE_VALUE')), \
                    contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
                self.assertEqual(probe.main(),1)
            self.assertEqual(out.getvalue(),'')
            self.assertEqual(err.getvalue(),'{"error":"KANIDM_CAPABILITY_PROBE_REFUSED"}\n')


if __name__=='__main__':unittest.main()
