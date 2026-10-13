"""Proxy HTTPS éphémère de fixture, jamais un transport d'exploitation.

Le navigateur résout Log/Vision vers loopback. Curl se connecte exclusivement
au Kanidm synthétique avec CA/SNI vérifiés. Les vraies redirections et tous les
Set-Cookie sont transmis, sans dépendre du routage partiel de Playwright.
"""
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ssl
import subprocess
import threading
from urllib.parse import parse_qs, urlsplit


class ProxyLocal:
    def __init__(self,n):
        self.captures=[];self.posts=[];self.paths=[];self.errors=[];self.n=n
    def __enter__(self):
        owner=self;n=self.n
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):self.checked()
            def do_POST(self):self.checked()
            def checked(self):
                try:self.forward()
                except (BrokenPipeError,ConnectionResetError,ssl.SSLEOFError):
                    # Navigation/fermeture annule normalement un asset chargé.
                    pass
                except Exception as e:
                    owner.errors.append(type(e).__name__)
                    self.send_error(502,'Transport fixture indisponible')
            def forward(self):
                host=self.headers.get('Host');u=urlsplit(self.path)
                if host=='vision.mrj.am' and u.path=='/auth/retour':
                    q=parse_qs(u.query);owner.captures.append(dict(state=q['state'][0],code=q['code'][0]))
                    self.send_response(200);self.send_header('Content-Length','7');self.end_headers();self.wfile.write(b'fixture');return
                if host!='log.mrj.am':self.send_error(403);return
                owner.paths.append(u.path)
                if self.command=='POST':owner.posts.append(u.path)
                def quote(v):
                    if any(ord(c)<32 or ord(c)==127 for c in v):raise ValueError('Option fixture invalide')
                    return '"'+v.replace('\\','\\\\').replace('"','\\"')+'"'
                cfg=['silent','show-error','proxy = ""','noproxy = "*"','proto = "=https"','tlsv1.2',
                     'max-time = 10','max-filesize = 1048576','dump-header = "-"','header = "Expect:"',
                     'url = '+quote('https://log.mrj.am'+self.path),
                     'connect-to = '+quote(f'log.mrj.am:443:127.0.0.1:{n.port}'),
                     'cacert = '+quote(str(n.ca)),'request = '+quote(self.command)]
                for k in ('Cookie','Origin','Content-Type','HX-Request','HX-Target','HX-Current-URL'):
                    v=self.headers.get(k)
                    if v:cfg.append('header = '+quote(k+': '+v))
                size=int(self.headers.get('Content-Length','0'))
                if size:cfg.append('data = '+quote(self.rfile.read(size).decode()))
                r=subprocess.run([str(n.curl),'--disable','--config','-'],input=('\n'.join(cfg)+'\n').encode(),
                                 capture_output=True,timeout=15)
                if r.returncode:raise ValueError('Transport fixture Native refusé')
                head,body=r.stdout.split(b'\r\n\r\n',1);statusline,headers=head.split(b'\r\n',1)
                self.send_response(int(statusline.split()[1]))
                for k,v in BytesParser().parsebytes(headers).items():
                    if k.lower() not in ('connection','content-length','transfer-encoding'):self.send_header(k,v)
                self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        self.server=ThreadingHTTPServer(('127.0.0.1',443),Handler)
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(str(n.ca),str(n.root/'key.pem'))
        self.server.socket=context.wrap_socket(self.server.socket,server_side=True)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();return self
    def __exit__(self,*args):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=3)
