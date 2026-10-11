"""IdP HTTP synthétique mutable ; aucun client, courriel ou compte externe."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import threading
from urllib.parse import urlsplit,parse_qs
import uuid

class IdP:
    def __init__(self):
        self.users={'sujet-alice':{'id':'sujet-alice','username':'alice','email':'alice@example.test','emailVerified':True,'enabled':True},
                    'non-verifie':{'id':'non-verifie','username':'autre','email':'unverified@example.test','emailVerified':False,'enabled':True}}
        self.creations=0;self.reset=[];app=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def reply(self,status,value=None,location=None):
                b=json.dumps(value).encode() if value is not None else b''
                self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(b)))
                if location:self.send_header('Location',location)
                self.end_headers();self.wfile.write(b)
            def do_POST(self):
                b=self.rfile.read(int(self.headers.get('Content-Length','0')))
                if self.path.endswith('/token'):return self.reply(200,{'access_token':'token-synthetique'})
                if self.path=='/admin/realms/mrjam/users':
                    p=json.loads(b);p['id']=str(uuid.uuid4());app.users[p['id']]=p;app.creations+=1
                    return self.reply(201,location='/admin/realms/mrjam/users/'+p['id'])
                self.reply(404)
            def do_GET(self):
                p=urlsplit(self.path);q=parse_qs(p.query)
                if p.path=='/admin/realms/mrjam/users':
                    return self.reply(200,[u for u in app.users.values() if all(u.get(k)==v[0] for k,v in q.items() if k in ('email','username'))])
                sid=p.path.rsplit('/',1)[-1]
                self.reply(200,app.users[sid]) if sid in app.users else self.reply(404)
            def do_PUT(self):
                p=urlsplit(self.path);b=self.rfile.read(int(self.headers.get('Content-Length','0')))
                if p.path.endswith('/execute-actions-email'):app.reset.append(p.path);return self.reply(204)
                sid=p.path.rsplit('/',1)[-1]
                if sid not in app.users:return self.reply(404)
                app.users[sid].update(json.loads(b));self.reply(204)
            def do_DELETE(self):
                sid=urlsplit(self.path).path.rsplit('/',1)[-1]
                self.reply(204 if app.users.pop(sid,None) else 404)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
    def __enter__(self):self.thread.start();return self
    def __exit__(self,*args):self.server.shutdown();self.thread.join(timeout=5);self.server.server_close()
