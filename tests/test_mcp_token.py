"""Séparation des tokens MCP, sessions web et identifiants Basic."""
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import threading
import time
import unittest
import urllib.request
import urllib.error
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from test_mrj_auth import AuthTests, module


class TokensTests(AuthTests):
    def test_cycle_token_et_separation(self):
        self.assertEqual(self.req('/auth/mcp-token')[0], 401)
        cookie, session = self.login()
        headers = {'Cookie': cookie, 'X-CSRF-Token': session['csrf']}
        self.assertEqual(self.req('/auth/mcp-token', {'action': 'creer'}, {'Cookie': cookie})[0], 403)
        self.assertEqual(self.req('/auth/mcp-token', {'action': 'creer'}, {**headers, 'Origin': 'https://evil.mrj.am'})[0], 403)
        status, _, result = self.req('/auth/mcp-token', {'action': 'creer'}, headers)
        self.assertEqual(status, 200)
        token = result['token']; bearer = {'Authorization': 'Bearer ' + token}
        self.assertEqual(self.req('/verify-mcp', headers=bearer)[0], 204)
        self.assertEqual(self.req('/verify-mcp', headers=bearer)[1]['X-Mrj-User'], 'test-user')
        self.assertEqual(self.req('/verify-mcp', headers=headers)[0], 401)
        self.assertEqual(self.req('/verify', headers=bearer)[0], 401)
        self.assertEqual(self.req('/auth/mcp-token', headers=bearer)[0], 401)
        self.assertEqual(self.req('/verify-mcp', headers=bearer, host='notes.mrj.am')[0], 401)
        self.assertEqual(self.req('/verify-mcp', headers={'Authorization': 'Bearer wrong'})[0], 401)
        self.assertEqual(self.req('/verify-mcp?token='+token)[0], 404)
        with self.sessions.connect() as db:
            row = db.execute('SELECT * FROM mcp_tokens').fetchone()
            self.assertEqual(row['digest'], hashlib.sha256(token.encode()).hexdigest())
            self.assertNotIn(token, str(dict(row)))
        self.assertNotIn('token', self.req('/auth/mcp-token', headers=headers)[2])
        nouveau = self.req('/auth/mcp-token', {'action': 'creer'}, headers)[2]['token']
        self.assertNotEqual(nouveau, token)
        self.assertEqual(self.req('/verify-mcp', headers=bearer)[0], 401)
        bearer = {'Authorization': 'Bearer ' + nouveau}
        self.assertEqual(self.req('/verify-mcp', headers=bearer)[0], 204)
        with patch.object(module.time, 'time', return_value=time.time()+module.DUREE_TOKEN_MCP+1):
            self.assertIsNone(self.sessions.verifier_token_mcp(bearer['Authorization']))
        self.assertEqual(self.req('/auth/mcp-token', {'action': 'revoquer'}, headers)[0], 200)
        self.assertEqual(self.req('/verify-mcp', headers=bearer)[0], 401)
        token = self.req('/auth/mcp-token', {'action': 'creer'}, headers)[2]['token']
        self.file.write_text('test-user:!\n')
        self.assertIsNone(self.sessions.verifier_token_mcp('Bearer '+token))

    def test_tokens_nommes_independants_et_migration_mistral(self):
        cookie, session = self.login()
        entetes = {'Cookie': cookie, 'X-CSRF-Token': session['csrf']}
        mistral = self.req('/auth/mcp-token', {'action': 'creer'}, entetes)[2]['token']
        avant = self.req('/auth/access-tokens', headers=entetes)[2]['tokens']
        self.assertEqual(len(avant), 1)
        self.assertEqual(avant[0]['name'], 'Mistral')
        self.assertEqual(self.req('/auth/access-tokens', {'action': 'creer', 'name': 'Mammouth'},
                                  {'Cookie': cookie})[0], 403)
        statut, _, cree = self.req('/auth/access-tokens',
                                   {'action': 'creer', 'name': 'Mammouth'}, entetes)
        self.assertEqual(statut, 200)
        mammouth = cree['token']
        self.assertEqual(len(mammouth), 43)
        for secret in (mistral, mammouth):
            self.assertEqual(self.req('/verify-mcp',
                                      headers={'Authorization': 'Bearer ' + secret})[0], 204)
        liste = self.req('/auth/access-tokens', headers=entetes)[2]['tokens']
        self.assertEqual({t['name'] for t in liste}, {'Mistral', 'Mammouth'})
        self.assertTrue(all(t['active'] for t in liste))
        self.assertTrue(all('token' not in t for t in liste))
        self.assertEqual(self.req('/auth/access-tokens',
                                  {'action': 'revoquer', 'id': cree['id']}, entetes)[0], 200)
        self.assertEqual(self.req('/verify-mcp',
                                  headers={'Authorization': 'Bearer ' + mammouth})[0], 401)
        self.assertEqual(self.req('/verify-mcp',
                                  headers={'Authorization': 'Bearer ' + mistral})[0], 204)
        statut, _, page = self.req_page('/auth/mcp')
        self.assertEqual(statut, 200)
        self.assertIn('Historique et gestion', page)
        self.assertIn('/auth/mcp.js', page)
        self.assertIn('/auth/style.css', page)
        self.assertEqual(self.req_page('/auth/style.css')[0], 200)

    def req_page(self, path):
        requete = urllib.request.Request(
            f'http://127.0.0.1:{self.server.server_port}{path}',
            headers={'X-Forwarded-Host': 'vision.mrj.am',
                     'X-Forwarded-Proto': 'https'})
        with urllib.request.urlopen(requete) as resultat:
            return resultat.status, resultat.headers, resultat.read().decode()

    def test_token_independant_de_la_session(self):
        cookie, session = self.login()
        headers = {'Cookie':cookie, 'X-CSRF-Token':session['csrf']}
        token = self.req('/auth/mcp-token', {'action':'creer'}, headers)[2]['token']
        self.req('/auth/logout', {}, headers)
        self.assertEqual(self.req('/verify-mcp', headers={'Authorization':'Bearer '+token})[0], 204)
        # Aucun secret conservé dans les assets ou dans un cookie.
        for nom in ('mcp.html','mcp.js'):
            self.assertNotIn(token, Path(module.__file__).with_name(nom).read_text())

    def test_nginx_basic_ou_bearer(self):
        nginx=shutil.which('nginx'); nix=shutil.which('nix-instantiate')
        if not nginx or not nix:self.skipTest('Nginx et Nix requis en CI')
        root=Path(__file__).resolve().parents[1]
        expression='(import ./apps/vision.nix { config = {}; }).services.nginx.virtualHosts."vision.mrj.am".locations'
        locations=json.loads(subprocess.check_output([nix,'--eval','--strict','--json','--expr',expression],cwd=root,text=True))
        class Backend(module.BaseHTTPRequestHandler):
            def do_POST(self):
                data=json.dumps({k:self.headers.get(k) for k in ('Authorization','Cookie','X-Vision-Authenticated','X-Vision-Browser','X-Mrj-User')}).encode()
                self.send_response(200);self.end_headers();self.wfile.write(data)
            def log_message(self,*args):pass
        backend=ThreadingHTTPServer(('127.0.0.1',0),Backend)
        threading.Thread(target=backend.serve_forever,daemon=True).start()
        self.addCleanup(backend.server_close);self.addCleanup(backend.shutdown)
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        conf=Path(self.tmp.name)/'nginx.conf'
        contenu=f'user root; master_process off; daemon off; pid {self.tmp.name}/nginx.pid; error_log {self.tmp.name}/error.log; events {{}} http {{ access_log off; client_body_temp_path {self.tmp.name}/body; proxy_temp_path {self.tmp.name}/proxy; fastcgi_temp_path {self.tmp.name}/fastcgi; uwsgi_temp_path {self.tmp.name}/uwsgi; scgi_temp_path {self.tmp.name}/scgi; limit_req_zone $binary_remote_addr zone=protected_api_per_ip:1m rate=10000r/s; limit_conn_zone $binary_remote_addr zone=protected_api_connections:1m; server {{ listen 127.0.0.1:{port};'
        for nom in ('= /mcp','= /_vision_mcp_token','@vision-mcp-authentication-required'):
            loc=locations[nom]
            extra=loc['extraConfig'].replace('X-Forwarded-Proto $scheme','X-Forwarded-Proto https').replace('/var/lib/vision/auth/htpasswd',str(self.file))
            proxy=loc.get('proxyPass','').replace('127.0.0.1:3002',f'127.0.0.1:{self.server.server_port}').replace('127.0.0.1:3001',f'127.0.0.1:{backend.server_port}')
            contenu+='location '+nom+' {'+('proxy_pass '+proxy+';' if proxy else '')+extra+'}'
        contenu+='location @vision-rate-limited { return 429; } }}'
        conf.write_text(contenu)
        proc=subprocess.Popen([nginx,'-p',self.tmp.name,'-c',str(conf)],stderr=subprocess.PIPE)
        def fermer():
            if proc.poll() is None:proc.terminate()
            proc.wait(timeout=5)
        self.addCleanup(fermer)
        def via(path='/mcp', headers=None):
            req=urllib.request.Request(f'http://127.0.0.1:{port}'+path,b'{}',{'Host':'vision.mrj.am',**(headers or {})})
            try:r=urllib.request.urlopen(req,timeout=3)
            except urllib.error.HTTPError as e:r=e
            with r:return r.status,r.read(),r.headers
        for _ in range(40):
            if proc.poll() is not None:self.fail(proc.stderr.read().decode())
            try:via();break
            except urllib.error.URLError:time.sleep(.05)
        cookie,session=self.login();headers={'Cookie':cookie,'X-CSRF-Token':session['csrf']}
        token=self.req('/auth/mcp-token',{'action':'creer'},headers)[2]['token']
        self.assertEqual(via()[0],401)
        self.assertIn('resource_metadata=',str(via()[2].get_all('WWW-Authenticate',[])))
        self.assertEqual(via(headers=headers)[0],401)
        self.assertEqual(via('/_vision_mcp_token')[0],404)
        self.assertEqual(via(headers={'X-Vision-Authenticated':'1','X-Vision-Browser':'1'})[0],401)
        self.assertEqual(via(headers={'Authorization':'Bearer wrong'})[0],401)
        for auth in ('Bearer '+token,'Basic '+base64.b64encode(('test-user:'+self.password).encode()).decode()):
            status,body,_=via(headers={'Authorization':auth,'Cookie':'forged','X-Vision-Browser':'1','X-Mrj-User':'forged'})
            self.assertEqual(status,200)
            self.assertEqual(json.loads(body),{'Authorization':None,'Cookie':None,'X-Vision-Authenticated':'1','X-Vision-Browser':None,'X-Mrj-User':'test-user'})
        self.sessions.token_mcp('test-user',revoquer=True)
        self.assertEqual(via(headers={'Authorization':'Bearer '+token})[0],401)


if __name__=='__main__':unittest.main()
