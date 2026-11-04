import importlib.util
import json
from pathlib import Path
import socket
import stat
import tempfile
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location('portal', Path(__file__).with_name('portal.py'))
P = importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)


class BoundaryTests(unittest.TestCase):
    def parse(self, raw):
        a, b = socket.socketpair()
        try:
            a.sendall(raw)
            a.shutdown(socket.SHUT_WR)
            return P.request(b)
        finally:
            a.close()
            b.close()

    def post(self, headers='', body=b'{}', target=None):
        return (f'POST {target or P.PREFIX + "api/begin"} HTTP/1.1\r\nHost: log.mrj.am\r\nOrigin: https://log.mrj.am\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\n{headers}\r\n').encode() + body

    def test_origin_framing_and_paths_closed(self):
        good = self.post(body=b'{"identity":"invented","access":null}')
        self.assertEqual(self.parse(good)[2]['identity'], 'invented')
        for raw in [good.replace(b'Origin: https://log.mrj.am', b'Origin: https://evil.test'),
                    good.replace(b'Host: log.mrj.am', b'Host: evil.test'),
                    self.post('Transfer-Encoding: chunked\r\n'), self.post('Content-Length: 2\r\n'),
                    self.post('Origin: https://log.mrj.am\r\n'), self.post('Sec-Fetch-Site: cross-site\r\n'),
                    self.post('Expect: 100-continue\r\n'), self.post(target='/v1/auth'),
                    self.post(target=P.PREFIX+'api/begin?x=y'), self.post(body=b'{"x":1,"x":2}'),
                    self.post(body=b'{"x":NaN}')]:
            with self.subTest(raw=raw[:35]), self.assertRaises(Exception):
                self.parse(raw)

    def test_cookie_and_authorization_not_forwarded(self):
        _, _, body = self.parse(self.post('Cookie: unrelated=synthetic\r\nAuthorization: Bearer synthetic\r\n'))
        self.assertEqual(body, {})

    def test_request_body_and_header_bounds(self):
        for raw in [self.post('X-Long: '+('a'*8192)+'\r\n'), self.post(body=b'a'*32769),
                    self.post(body=b'{}')[:-1], b'GET '+b'a'*4096+b' HTTP/1.1\r\n\r\n']:
            with self.assertRaises(Exception):
                self.parse(raw)

    def test_invalid_actions_never_contact_provider(self):
        calls = []
        p = P.Portal(lambda *a, **k: calls.append((a,k)), lambda *_: self.fail('delivery'))
        for action, body in [('begin', {'identity':'../admin','access':None}),
                             ('begin', {'identity':'admin','access':None,'url':'https://elsewhere'}),
                             ('commit', {'transaction':'A'*43}), ('assert', {'transaction':'A'*43})]:
            with self.assertRaises(Exception):
                p.act(action, body)
        self.assertEqual(calls, [])

    def test_expired_transaction_revokes_and_forgets(self):
        calls = []
        p = P.Portal(lambda *a, **k: calls.append((a,k)), None)
        p.transactions['A'*43] = {'deadline':time.monotonic()-1,'tokens':['synthetic.jwt.token'],'caches':[b'synthetic']}
        p.expire()
        self.assertEqual(len(calls), 1)
        self.assertEqual(p.transactions['A'*43]['stage'], 'expired')
        self.assertEqual(p.transactions['A'*43]['tokens'], [])
        self.assertEqual(p.act('commit', {'transaction':'A'*43}), {'status':'EXPIRED'})

    def test_failed_revocation_kept_for_retry(self):
        def unavailable(*_, **__):
            raise OSError()
        p = P.Portal(unavailable, None)
        state = {'tokens':['synthetic.jwt.token'],'caches':[b'synthetic']}
        self.assertFalse(p.revoke(state))
        self.assertEqual(state['tokens'], ['synthetic.jwt.token'])
        self.assertEqual(state['caches'], [])

    def test_api_allowlist_rejects_admin_and_password(self):
        api = object.__new__(P.Api)
        for args in [('GET','/v1/group/idm_admins'), ('POST','/v1/person',{}),
                     ('POST','/v1/auth',{'step':{'begin':'password'}}),
                     ('POST','/v1/auth',{'step':{'init2':{'username':'admin','issue':'cookie','privileged':True}}})]:
            with self.assertRaises(P.Refused):
                api(*args)

    def test_delivery_fixed_invocation_modes_and_cleanup(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / 'login'
            calls = []
            def run(argv, **kwargs):
                calls.append(argv)
                self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o700)
                self.assertEqual(set(p.name for p in target.iterdir()), {'identity.json','access.json'})
                for name, data in [('identity.json',b'one'),('access.json',b'two')]:
                    self.assertEqual((target/name).read_bytes(), data)
                    self.assertEqual(stat.S_IMODE((target/name).stat().st_mode), 0o600)
                self.assertEqual(kwargs['timeout'],145)
                self.assertNotIn('shell',kwargs)
                return SimpleNamespace(returncode=0)
            with patch.object(P,'DIRECTORY',target), patch.object(P.subprocess,'run',run):
                P.Delivery('/nix/store/invented/bin/systemctl')(b'one',b'two')
            self.assertEqual(calls,[['/nix/store/invented/bin/systemctl','start',P.UNIT]])
            self.assertFalse(target.exists())

    def test_delivery_failure_cleans_only_own_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / 'login'
            with patch.object(P,'DIRECTORY',target), patch.object(P.subprocess,'run',return_value=SimpleNamespace(returncode=1)):
                with self.assertRaises(P.Refused):
                    P.Delivery('/nix/store/invented/bin/systemctl')(b'one',b'two')
                self.assertFalse(target.exists())
                target.mkdir()
                (target/'unrelated').write_text('preserve')
                with self.assertRaises(FileExistsError):
                    P.Delivery('/nix/store/invented/bin/systemctl')(b'one',b'two')
                self.assertEqual((target/'unrelated').read_text(),'preserve')


# These are state-machine tests with an explicitly invented provider. Real
# cryptographic assertions and actual provider permissions are qualified apart.
class PermissionStateTests(unittest.TestCase):
    IDENTITY={'idm_admins','idm_service_account_admins'}
    ACCESS={'idm_access_control_admins'}

    def setUp(self):
        import base64
        self.b64=lambda raw:base64.urlsafe_b64encode(raw).rstrip(b'=').decode()
        self.clock=100.
        self.wall=10000.
        self.groups={'identity':set(self.IDENTITY),'access':set(self.ACCESS),'none':set()}
        self.current=None
        self.revoked=[]
        self.deliveries=[]
        self.challenge=self.b64(b'x'*32)
        self.tokens={name:self.b64(b'{}')+'.'+self.b64(json.dumps({'expiry':10900,'spn':name+'@log.mrj.am'}).encode())+'.c2ln' for name in self.groups}
        def api(method,path,body=None,session=None,token=None):
            if path=='/v1/logout':self.revoked.append(token);return {},None
            if path=='/v1/self':
                name=next(name for name,value in self.tokens.items() if token==value)
                return {'youare':{'attrs':{'memberof':sorted(self.groups[name])}}},None
            step=body['step']
            if 'init2' in step:
                self.current=step['init2']['username']
                return {'state':{'choose':['passkey']}},'synthetic.session.value'
            if 'begin' in step:
                return {'state':{'continue':[{'passkey':{'publicKey':{'rpId':'log.mrj.am','challenge':self.challenge}}}]}},'synthetic.session.value'
            return {'state':{'success':self.tokens[self.current]}},None
        for target,value in ((P.time,'monotonic'),(P.time,'time')):
            patcher=patch.object(target,value,side_effect=(lambda:self.clock) if value=='monotonic' else (lambda:self.wall))
            patcher.start();self.addCleanup(patcher.stop)
        patcher=patch.object(P,'verified_cache',side_effect=lambda *_:b'INVENTED_VERIFIED_CACHE')
        patcher.start();self.addCleanup(patcher.stop)
        self.portal=P.Portal(api,lambda *cache:self.deliveries.append(cache))

    def begin(self,name='identity',access=None):
        value=self.portal.act('begin',{'identity':name,'access':access})
        self.nonce=value['transaction'];return value

    def assertion(self):
        client={'type':'webauthn.get','origin':P.ORIGIN,'challenge':self.challenge,'crossOrigin':False}
        return self.portal.act('assert',{'transaction':self.nonce,'assertion':{'id':'YQ','rawId':'YQ','type':'public-key',
          'response':{'authenticatorData':self.b64(b'x'*37),'clientDataJSON':self.b64(json.dumps(client).encode()),'signature':self.b64(b'x'*8),'userHandle':None}}})

    def test_authentication_without_identity_rights_never_ready(self):
        self.begin('none');result=self.assertion()
        self.assertEqual(result,{'status':'IDENTITY_RIGHTS_REQUIRED','permissions':{'identity_services':False,'identity_admins':False,'mail_group_management':False}})
        self.assertEqual(self.deliveries,[]);self.assertEqual(self.revoked,[self.tokens['none']])

    def test_service_management_without_identity_administration_refused(self):
        self.groups['identity']={'idm_service_account_admins'}|self.ACCESS
        self.begin();result=self.assertion()
        self.assertEqual(result['status'],'IDENTITY_RIGHTS_REQUIRED')
        self.assertTrue(result['permissions']['identity_services']);self.assertFalse(result['permissions']['identity_admins'])
        self.assertEqual(self.deliveries,[])

    def test_access_continuation_reuses_first_fresh_session(self):
        self.begin();result=self.assertion()
        self.assertEqual(result['status'],'ACCESS_REQUIRED')
        first=self.portal.transactions[self.nonce]['tokens'][0]
        self.assertEqual(self.revoked,[])
        result=self.portal.act('access',{'transaction':self.nonce,'access':'access'})
        self.assertEqual(result['account'],2)
        result=self.assertion();self.assertEqual(result['status'],'READY')
        self.assertEqual(self.portal.transactions[self.nonce]['tokens'][0],first)
        self.assertTrue(all(result['permissions'].values()))
        self.assertEqual(self.portal.act('commit',{'transaction':self.nonce}),{'status':'COMPLETE'})
        self.assertEqual(len(self.deliveries),1)
        self.assertEqual(set(self.revoked),{self.tokens['identity'],self.tokens['access']})

    def test_wrong_second_account_is_explicitly_refused(self):
        self.begin(access='none');self.assertion();result=self.assertion()
        self.assertEqual(result['status'],'ACCESS_RIGHTS_REQUIRED')
        self.assertEqual(self.deliveries,[])
        self.assertEqual(set(self.revoked),{self.tokens['identity'],self.tokens['none']})

    def test_right_removed_after_ready_refuses_commit_without_delivery(self):
        self.groups['identity']|=self.ACCESS
        self.begin();self.assertEqual(self.assertion()['status'],'READY')
        self.groups['identity']-=self.ACCESS
        result=self.portal.act('commit',{'transaction':self.nonce})
        self.assertEqual(result['status'],'ACCESS_RIGHTS_REQUIRED');self.assertEqual(self.deliveries,[])

    def test_expired_ready_returns_explicit_status_and_revokes(self):
        self.groups['identity']|=self.ACCESS
        self.begin();self.assertion();self.clock=401.
        self.assertEqual(self.portal.act('commit',{'transaction':self.nonce}),{'status':'EXPIRED'})
        self.assertEqual(self.deliveries,[]);self.assertEqual(self.revoked,[self.tokens['identity']])

    def test_renewal_only_after_authentication_and_capped_by_global_and_session(self):
        self.begin();self.clock=350.
        result=self.assertion();self.assertEqual(result['expires_in'],300)
        self.clock=400.
        self.portal.act('access',{'transaction':self.nonce,'access':'access'})
        self.assertEqual(self.portal.transactions[self.nonce]['deadline'],650.)
        self.clock=600.;self.wall=10500.
        result=self.assertion()
        self.assertEqual(result['expires_in'],250)  # earliest JWT expiry minus fixed unit margin
        self.assertEqual(self.portal.transactions[self.nonce]['deadline'],850.)
        self.portal.created=-100.
        self.assertEqual(self.portal.lifetime(self.portal.transactions[self.nonce]),50)

    def test_second_account_route_rejects_same_identity_and_unbounded_fields(self):
        self.begin();self.assertion()
        for body in ({'transaction':self.nonce,'access':'identity'}, {'transaction':self.nonce,'access':'access','url':'https://elsewhere'}):
            with self.assertRaises(P.Refused):self.portal.act('access',body)
        self.assertEqual(self.deliveries,[])

    # Native inheritance is proved independently with a real provider.
    def test_idm_admin_inherited_group_authority_needs_no_second_account(self):
        self.groups['identity'].add('idm_group_admins')
        self.begin();result=self.assertion()
        self.assertEqual(result['status'],'READY')
        self.assertTrue(result['permissions']['mail_group_management'])
        self.assertNotIn('idm_access_control_admins',self.groups['identity'])
        self.assertEqual(self.portal.act('commit',{'transaction':self.nonce}),{'status':'COMPLETE'})
        self.assertEqual(len(self.deliveries),1)


if __name__ == '__main__':
    unittest.main()
