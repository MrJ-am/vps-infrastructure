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
        self.assertEqual(p.transactions, {})

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


if __name__ == '__main__':
    unittest.main()
