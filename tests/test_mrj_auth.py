import importlib.util
import json
import os
import shutil
import socket
import subprocess
from pathlib import Path
import tempfile
import threading
import time
import unittest
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('mrj_auth',Path(__file__).resolve().parents[1]/'services/mrj-auth/server.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class AuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.file=Path(self.tmp.name)/'htpasswd';self.password='test-only-random-password-123456'
        self.file.write_text('test-user:'+module.sha512_crypt.using(rounds=5000).hash(self.password)+'\n')
        self.sessions=module.Sessions(Path(self.tmp.name)/'sessions.sqlite',self.file,'mrj.am',['vision.mrj.am','notes.mrj.am'])
        self.server=ThreadingHTTPServer(('127.0.0.1',0),module.Handler);self.server.sessions=self.sessions
        thread=threading.Thread(target=self.server.serve_forever,daemon=True);thread.start()
        self.addCleanup(self.server.server_close);self.addCleanup(self.server.shutdown)
    def req(self,path,data=None,headers=None,host='vision.mrj.am'):
        base={'X-Forwarded-Host':host,'X-Forwarded-Proto':'https','X-Real-IP':'127.0.0.1','Origin':'https://'+host}
        if data is not None:base['Content-Type']='application/json'
        base.update(headers or {})
        req=urllib.request.Request(f'http://127.0.0.1:{self.server.server_port}{path}',None if data is None else json.dumps(data).encode(),base)
        try:r=urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:r=e
        with r:
            body=r.read();return r.status,r.headers,json.loads(body) if body else None
    def login(self):
        status,headers,body=self.req('/auth/login',{'username':'test-user','password':self.password})
        self.assertEqual(status,200);return headers['Set-Cookie'],body
    def test_shared_session_csrf_and_logout(self):
        self.assertEqual(self.req('/verify')[0],401)
        cookie,body=self.login()
        for flag in ['Domain=mrj.am','Secure','HttpOnly','SameSite=Lax','Path=/']:self.assertIn(flag,cookie)
        self.assertEqual(self.req('/auth/session',headers={'Cookie':cookie},host='notes.mrj.am')[2]['username'],'test-user')
        base={'Cookie':cookie,'X-Original-Method':'POST'}
        self.assertEqual(self.req('/verify',headers=base)[0],403)
        base['X-CSRF-Token']=body['csrf']
        self.assertEqual(self.req('/verify',headers=base)[0],204)
        self.assertEqual(self.req('/verify',headers={**base,'Origin':'https://evil.mrj.am'})[0],403)
        self.assertEqual(self.req('/verify',headers=base,host='evil.mrj.am')[0],403)
        self.assertEqual(self.req('/auth/logout',{},headers={'Cookie':cookie})[0],403)
        self.assertEqual(self.req('/auth/logout',{},headers=base)[0],200)
        self.assertEqual(self.req('/auth/session',headers={'Cookie':cookie},host='notes.mrj.am')[0],401)
    def test_rotation_expiry_fixation_and_no_clear_token_at_rest(self):
        cookie,body=self.login();token=self.sessions.token(cookie)
        with self.sessions.connect() as db:
            row=db.execute('SELECT * FROM sessions').fetchone();self.assertNotEqual(row['digest'],token)
        # A second login rotates and revokes the supplied old session.
        status,headers,new=self.req('/auth/login',{'username':'test-user','password':self.password},headers={'Cookie':cookie})
        self.assertEqual(status,200);self.assertNotEqual(headers['Set-Cookie'],cookie)
        self.assertIsNone(self.sessions.session(cookie))
        newcookie=headers['Set-Cookie'];self.file.write_text('test-user:'+module.sha512_crypt.using(rounds=5000).hash(self.password+'x')+'\n')
        self.assertIsNone(self.sessions.session(newcookie))
        self.password+='x';cookie,_=self.login()
        with patch.object(module.time,'time',return_value=time.time()+module.IDLE+1):self.assertIsNone(self.sessions.session(cookie))
        self.assertIsNone(self.sessions.session(cookie+'; '+cookie))
    def test_login_origin_blocked_accounts_and_rate_limit(self):
        data={'username':'test-user','password':self.password}
        self.assertEqual(self.req('/auth/login',data,headers={'Origin':'https://notes.mrj.am'})[0],403)
        self.assertEqual(self.req('/auth/login',data,headers={'X-Forwarded-Proto':'http'})[0],403)
        for _ in range(10):self.assertEqual(self.req('/auth/login',{**data,'password':'wrong'})[0],401)
        self.assertEqual(self.req('/auth/login',data)[0],429)
        self.file.write_text('vision-bootstrap-locked:'+module.sha512_crypt.using(rounds=5000).hash(self.password)+'\n')
        self.assertEqual(self.req('/auth/login',{'username':'vision-bootstrap-locked','password':self.password},headers={'X-Real-IP':'127.0.0.2'})[0],401)

class NginxGateTests(unittest.TestCase):
    setUp = AuthTests.setUp
    def test_real_nginx_session_gate(self):
        nginx=os.environ.get('TEST_NGINX') or shutil.which('nginx')
        nix=os.environ.get('TEST_NIX') or shutil.which('nix-instantiate')
        if not nginx or not nix:self.skipTest('Nginx et Nix requis pour le test de passerelle')
        root=Path(__file__).resolve().parents[1]
        expression='let c = import ./modules/mrj-auth.nix { config.infrastructure.gateway.projects = builtins.fromJSON (builtins.readFile ./projects.json); pkgs = {}; lib = { filter = builtins.filter; mkIf = a: b: if a then b else {}; }; }; in c.services.nginx.virtualHosts."vision.mrj.am".locations'
        locations=json.loads(subprocess.check_output([nix,'--eval','--strict','--json','--expr',expression],cwd=root,text=True))
        class Backend(module.BaseHTTPRequestHandler):
            def do_POST(self):
                body=json.dumps({'user':self.headers.get('X-Mrj-User'),'browser':self.headers.get('X-Vision-Browser'),'auth':self.headers.get('X-Vision-Authenticated')}).encode()
                self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
            def log_message(self,*args):pass
        backend=ThreadingHTTPServer(('127.0.0.1',0),Backend)
        threading.Thread(target=backend.serve_forever,daemon=True).start()
        self.addCleanup(backend.server_close);self.addCleanup(backend.shutdown)
        with socket.socket() as socket_:
            socket_.bind(('127.0.0.1',0));port=socket_.getsockname()[1]
        conf=Path(self.tmp.name)/'nginx.conf'
        text=f'user root; master_process off; daemon off; pid {self.tmp.name}/nginx.pid; error_log {self.tmp.name}/error.log; events {{}} http {{ access_log off; client_body_temp_path {self.tmp.name}/body; proxy_temp_path {self.tmp.name}/proxy; fastcgi_temp_path {self.tmp.name}/fastcgi; uwsgi_temp_path {self.tmp.name}/uwsgi; scgi_temp_path {self.tmp.name}/scgi; limit_req_zone $binary_remote_addr zone=protected_api_per_ip:1m rate=1000r/s; server {{ listen 127.0.0.1:{port}; server_name vision.mrj.am notes.mrj.am;'
        for name,location in locations.items():
            extra=location['extraConfig'].replace('X-Forwarded-Proto $scheme','X-Forwarded-Proto https')
            proxy=location.get('proxyPass','').replace('127.0.0.1:3002',f'127.0.0.1:{self.server.server_port}').replace('127.0.0.1:3001',f'127.0.0.1:{backend.server_port}')
            text+='location '+name+' {'+('proxy_pass '+proxy+';' if proxy else '')+extra+'}'
        conf.write_text(text+'}}')
        process=subprocess.Popen([nginx,'-p',self.tmp.name,'-c',str(conf)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        self.addCleanup(lambda:process.poll() is None and process.terminate())
        def via(path,data=None,headers=None):
            req=urllib.request.Request(f'http://127.0.0.1:{port}'+path,None if data is None else json.dumps(data).encode(),{'Host':'vision.mrj.am','Origin':'https://vision.mrj.am','Content-Type':'application/json',**(headers or {})})
            try:r=urllib.request.urlopen(req,timeout=3)
            except urllib.error.HTTPError as e:r=e
            with r:
                body=r.read();return r.status,r.headers,json.loads(body) if body and r.headers.get_content_type()=='application/json' else None
        for _ in range(30):
            if process.poll() is not None:self.fail(process.stderr.read().decode())
            try:
                status,_,_=via('/auth/session');break
            except urllib.error.URLError:time.sleep(.05)
        self.assertEqual(status,401)
        self.assertEqual(via('/_mrj_session')[0],404)
        self.assertEqual(via('/api/web/list',{}, {'X-Vision-Authenticated':'1','X-Vision-Browser':'1','X-Mrj-User':'forged'})[0],401)
        status,headers,body=via('/auth/login',{'username':'test-user','password':self.password});self.assertEqual(status,200)
        cookie=headers['Set-Cookie'].split(';')[0]
        self.assertEqual(via('/api/web/list',{}, {'Cookie':cookie})[0],403)
        status,_,result=via('/api/web/list',{}, {'Cookie':cookie,'X-CSRF-Token':body['csrf'],'X-Mrj-User':'forged'})
        self.assertEqual(status,200);self.assertEqual(result,{'user':'test-user','browser':'1','auth':'1'})
        self.assertEqual(via('/api/web/list',{}, {'Cookie':cookie,'X-CSRF-Token':body['csrf'],'Origin':'https://evil.mrj.am'})[0],403)
        process.terminate();process.wait(timeout=5)

if __name__=='__main__':unittest.main()
