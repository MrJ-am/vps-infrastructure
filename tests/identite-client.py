"""Contrat HTTP du client provisoire, IdP synthétique loopback, aucun compte réel."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading

ROOT=Path(__file__).resolve().parents[1]
def verifier():
    calls=[]
    class IdP(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,status,value=None,location=None):
            body=json.dumps(value).encode() if value is not None else b''
            self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)))
            if location:self.send_header('Location',location)
            self.end_headers();self.wfile.write(body)
        def do_POST(self):
            p=self.rfile.read(int(self.headers.get('Content-Length','0')))
            calls.append((self.command,self.path,self.headers.get('Authorization'),p))
            if self.path=='/realms/mrjam/protocol/openid-connect/token':self.reply(200,{'access_token':'token-synthetique'})
            elif self.path=='/admin/realms/mrjam/users':self.reply(201,location='/admin/realms/mrjam/users/sujet-neuf')
            else:self.reply(404)
        def do_GET(self):
            calls.append((self.command,self.path,self.headers.get('Authorization'),None))
            if self.path=='/admin/realms/mrjam/users/sujet-alice':self.reply(200,{'id':'sujet-alice','emailVerified':True,'email':'alice@example.test'})
            elif self.path=='/admin/realms/mrjam/users/sujet-non-verifie':self.reply(200,{'id':'sujet-non-verifie','emailVerified':False,'email':'alice@example.test'})
            elif self.path=='/admin/realms/mrjam/users/sujet-incompatible':self.reply(200,{'id':'sujet-bob','emailVerified':True,'email':'bob@example.test'})
            else:self.reply(404)
    with ThreadingHTTPServer(('127.0.0.1',0),IdP) as server,tempfile.TemporaryDirectory(prefix='identite-client-') as d:
        t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
        def lit(s):return '"'+str(s).replace('\\','\\\\').replace('"','\\"')+'"'
        runner=Path(d)/'verifier.lisp';runner.write_text(f'''(load {lit(ROOT/'assemblage/charger.lisp')})
(asdf:load-system "mrjam-identite")
(mrjam-native:initialiser-crypto {lit(os.environ.get('MRJAM_LIBCRYPTO','/lib/x86_64-linux-gnu/libcrypto.so.3'))})
(let* ((c (mrjam-identite:faire-client "mrjam-cycle" (make-string 43 :initial-element #\\a) {lit(shutil.which('curl'))} :base "http://127.0.0.1:{server.server_port}"))
       (d (vision:jobject "emetteur" mrjam-identite:issuer "sujet" "sujet-alice")))
  (assert (equal "alice@example.test" (mrjam-identite:adresse-verifiee c d)))
  (dolist (s '("sujet-non-verifie" "sujet-incompatible" "absent"))
    (assert (handler-case (progn (mrjam-identite:adresse-verifiee c (vision:jobject "emetteur" mrjam-identite:issuer "sujet" s)) nil) (mrjam-identite:identite-error () t))))
  (assert (handler-case (progn (mrjam-identite:adresse-verifiee c (vision:jobject "emetteur" "https://autre.example.test" "sujet" "sujet-alice")) nil) (mrjam-identite:identite-error () t)))
  (assert (handler-case (progn (mrjam-identite:requete c "GET" "http://autre.example.test") nil) (mrjam-identite:identite-error () t)))
  (assert (handler-case (progn (mrjam-identite:requete c "GET" "/admin/realms/mrjam/users/../clients") nil) (mrjam-identite:identite-error () t)))
  (let ((r (mrjam-identite:requete c "POST" "/admin/realms/mrjam/users" :token (mrjam-identite:autorisation c) :json (vision:jobject "username" "admission-synthetique"))))
    (assert (= 201 (mrjam-identite:reponse-statut r)))
    (assert (equal "/admin/realms/mrjam/users/sujet-neuf" (mrjam-identite:reponse-location r))))
  (assert (equal "alice%2B%C3%A9%40example.test" (mrjam-identite:parametre-url "alice+é@example.test")))
  (format t "Client provisoire : adresse vérifiée, issuer/sujet, erreurs et Location contrôlés.~%"))
''')
        try:subprocess.run([os.environ.get('SBCL','sbcl'),'--script',str(runner)],check=True)
        finally:server.shutdown();t.join(timeout=5)
        assert len(calls)==10
        for method,path,auth,body in calls:
            if path.endswith('/token'):assert auth is None and b'grant_type=client_credentials' in body
            else:assert auth=='Bearer token-synthetique'
    print('Dix échanges HTTP synthétiques ; aucun IdP réel contacté, aucun secret en argument.')
if __name__=='__main__':verifier()
