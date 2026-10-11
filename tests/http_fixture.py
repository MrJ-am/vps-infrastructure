"""Entrée HTTP loopback de test vers le vrai artefact AF_UNIX, sans IdP simulé.

Ce transport de fixture ne fait pas partie du serveur livré ni de l'exploitation.
Les contrôles Nginx/OIDC restent des suites distinctes.
"""
from contextlib import contextmanager
import http.client
import http.server
from pathlib import Path
import socket
import threading
from urllib.parse import urlsplit


@contextmanager
def entree(socket_path, statique, prefix='/matheval', service='matheval', preparer=None,port=0):
    class Unix(http.client.HTTPConnection):
        def connect(self):
            self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
            self.sock.settimeout(15)
            self.sock.connect(str(socket_path))
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(statique),**kwargs)
        def log_message(self,*args):pass # Aucun cookie, corps ou chemin personnel journalisé.
        def translate_path(self,path):
            path=urlsplit(path).path
            if path.startswith(prefix+'/'):path=path[len(prefix):]
            return super().translate_path(path)
        def transmettre(self):
            api=urlsplit(self.path).path.startswith(prefix+'/api/') if service=='matheval' else urlsplit(self.path).path.startswith(('/api/','/mcp','/healthz'))
            if not api:
                if self.command in ('GET','HEAD'):return getattr(super(),'do_'+self.command)()
                return self.send_error(404)
            taille=int(self.headers.get('Content-Length','0'))
            if not 0<=taille<=5*1024*1024:return self.send_error(413)
            corps=self.rfile.read(taille)
            if preparer:preparer(self.headers)
            headers={k:v for k,v in self.headers.items() if k.lower() not in
                     ('connection','transfer-encoding','content-length','x-mrjam-service')}
            headers['X-Mrjam-Service']=service
            c=Unix('localhost',timeout=15)
            try:
                c.request(self.command,self.path,body=corps,headers=headers)
                r=c.getresponse();contenu=r.read()
                self.send_response(r.status)
                for k,v in r.getheaders():
                    if k.lower() not in ('connection','transfer-encoding','content-length','server','date'):
                        self.send_header(k,v)
                self.send_header('Content-Length',str(len(contenu)));self.end_headers()
                if self.command!='HEAD':
                    try:self.wfile.write(contenu)
                    except (BrokenPipeError,ConnectionResetError):pass # Panne simulée côté navigateur.
            finally:c.close()
        do_GET=do_HEAD=do_POST=do_PUT=do_DELETE=transmettre
    server=http.server.ThreadingHTTPServer(('127.0.0.1',port),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:yield 'http://127.0.0.1:'+str(server.server_port)
    finally:server.shutdown();server.server_close();thread.join(timeout=5)
