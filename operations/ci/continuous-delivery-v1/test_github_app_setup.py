import http.client,importlib.util,json,os,stat,tempfile,threading,unittest
from pathlib import Path
from http.server import HTTPServer

spec=importlib.util.spec_from_file_location('setup',Path(__file__).with_name('github-app-setup.py'))
S=importlib.util.module_from_spec(spec);spec.loader.exec_module(S)

def fixture():
    # Syntactically shaped synthetic material, never a usable signing key.
    return {'id':123,'owner':{'id':S.OWNER_ID,'login':S.OWNER},'slug':'synthetic-app',
            'html_url':'https://github.com/apps/synthetic-app','permissions':dict(S.PERMISSIONS),
            'events':[],'pem':'-----BEGIN PRIVATE KEY-----\n'+'A'*1500+'\n-----END PRIVATE KEY-----\n',
            'client_secret':'SYNTHETIC_NOT_RETAINED','webhook_secret':'SYNTHETIC_NOT_RETAINED'}

class SetupTests(unittest.TestCase):
    def test_permissions_and_owner_are_fixed(self):
        for mutate in [lambda v:v['owner'].update(id=1),lambda v:v['permissions'].update(administration='write'),
                       lambda v:v.update(html_url='https://other.invalid'),lambda v:v.update(events=['push'])]:
            value=fixture();mutate(value)
            with self.assertRaises(S.Refused):S.checked_response(value)
    def test_unused_secrets_are_not_retained(self):
        value=S.checked_response(fixture())
        self.assertNotIn('client_secret',value);self.assertNotIn('webhook_secret',value)
    def test_private_store_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);S.save_private(root,S.checked_response(fixture()))
            self.assertEqual(stat.S_IMODE((root/'app-credentials.json').stat().st_mode),0o600)
            with self.assertRaises(FileExistsError):S.save_private(root,S.checked_response(fixture()))
            root.chmod(0o755)
            with self.assertRaises(S.Refused):S.save_private(root,S.checked_response(fixture()))
    def test_real_http_handshake_cookie_state_and_replay(self):
        with tempfile.TemporaryDirectory() as name:
            calls=[]
            def exchange(code):calls.append(code);return S.checked_response(fixture())
            setup=S.Setup(Path(name),exchange)
            server=HTTPServer(('127.0.0.1',0),S.handler(setup))
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            def get(path,cookie=None,host=f'127.0.0.1:{S.PORT}'):
                connection=http.client.HTTPConnection(*server.server_address,timeout=5)
                headers={'Host':host}
                if cookie:headers['Cookie']=cookie
                connection.request('GET',path,headers=headers);r=connection.getresponse()
                result=(r.status,dict(r.getheaders()),r.read());connection.close();return result
            try:
                self.assertEqual(get('/start?state='+setup.state,host='foreign.invalid')[0],400)
                status,headers,body=get('/start?state='+setup.state)
                self.assertEqual(status,200);self.assertIn('HttpOnly',headers['Set-Cookie'])
                self.assertNotIn(b'PRIVATE KEY',body)
                path='/callback?state='+setup.state+'&code='+'a'*40
                self.assertEqual(get(path)[0],400);self.assertEqual(calls,[])
                self.assertEqual(get(path,'mrjam_setup=wrong')[0],400);self.assertEqual(calls,[])
                status,_,body=get(path,'mrjam_setup='+setup.state)
                self.assertEqual(status,200);self.assertEqual(len(calls),1)
                self.assertNotIn(b'PRIVATE KEY',body);self.assertNotIn(b'SYNTHETIC_NOT_RETAINED',body)
                self.assertEqual(get(path,'mrjam_setup='+setup.state)[0],400)
                self.assertEqual(len(calls),1)
            finally:server.shutdown();server.server_close();thread.join()
    def test_expired_session_never_exchanges(self):
        with tempfile.TemporaryDirectory() as name:
            setup=S.Setup(Path(name),lambda _:self.fail('exchange forbidden'));setup.deadline=0
            with self.assertRaisesRegex(S.Refused,'SESSION_EXPIRED'):setup.complete(setup.state,setup.state,'a'*40)

if __name__=='__main__':unittest.main()
