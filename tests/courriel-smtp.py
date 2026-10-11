"""Vrai curl et STARTTLS, relais synthétique loopback, certificats de test isolés."""
import json
import os
from pathlib import Path
import shutil
import socketserver
import ssl
import subprocess
import tempfile
import threading

ROOT=Path(__file__).resolve().parents[1]

def verifier():
    with tempfile.TemporaryDirectory(prefix='courriel-starttls-') as d:
        root=Path(d);os.chmod(root,0o700)
        key=root/'cle.pem';cert=root/'certificat.pem'
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(key),'-out',str(cert),'-days','1',
                        '-subj','/CN=smtp.protonmail.ch','-addext','subjectAltName=DNS:smtp.protonmail.ch'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        badkey=root/'mauvaise-cle.pem';badreq=root/'mauvaise.csr';badcert=root/'mauvais-hote.pem'
        subprocess.run(['openssl','req','-new','-newkey','rsa:2048','-nodes','-keyout',str(badkey),'-out',str(badreq),'-subj','/CN=wrong.example.test'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        ext=root/'extensions';ext.write_text('subjectAltName=DNS:wrong.example.test\n')
        subprocess.run(['openssl','x509','-req','-in',str(badreq),'-CA',str(cert),'-CAkey',str(key),'-CAcreateserial','-out',str(badcert),'-days','1','-extfile',str(ext)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        state={'auth_tls':0,'data':0,'auth_plain':0};connections=[0]
        class Relais(socketserver.StreamRequestHandler):
            def handle(self):
                connections[0]+=1;index=connections[0]
                tls=False;auth_pending=False;self.connection.settimeout(5)
                def send(data):self.wfile.write(data.encode());self.wfile.flush()
                send('220 relais synthétique\r\n')
                try:
                    while True:
                        raw=self.rfile.readline(8192)
                        if not raw:return
                        cmd=raw.decode().strip();upper=cmd.upper()
                        if auth_pending:
                            auth_pending=False;send('235 Authentifié\r\n')
                        elif upper.startswith('EHLO'):
                            send('250-local.test\r\n250-STARTTLS\r\n250 AUTH PLAIN\r\n')
                        elif upper=='STARTTLS':
                            send('220 TLS requis\r\n')
                            context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                            context.load_cert_chain(badcert if index==3 else cert,badkey if index==3 else key)
                            self.connection=context.wrap_socket(self.connection,server_side=True)
                            self.rfile=self.connection.makefile('rb');self.wfile=self.connection.makefile('wb');tls=True
                        elif upper.startswith('AUTH '):
                            state['auth_tls' if tls else 'auth_plain']+=1
                            if not tls:send('530 TLS requis\r\n')
                            elif len(cmd.split())==2:auth_pending=True;send('334 \r\n')
                            else:send('235 Authentifié\r\n')
                        elif upper.startswith(('MAIL FROM:','RCPT TO:')):send('250 Accepté\r\n')
                        elif upper=='DATA':
                            send('354 Message\r\n');count=0
                            while self.rfile.readline(8192)!=b'.\r\n':
                                count+=1
                                if count>10000:raise AssertionError('Message non borné')
                            state['data']+=1;send('250 Accepté par le relais\r\n')
                        elif upper=='QUIT':send('221 Fin\r\n');return
                        else:send('500 Refusé\r\n')
                except (OSError,ssl.SSLError):return
        class Serveur(socketserver.ThreadingTCPServer):
            daemon_threads=True
        with Serveur(('127.0.0.1',0),Relais) as server:
            port=server.server_address[1];thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            wrapper=root/'curl-local';wrapper.write_text('#!/bin/sh\nexec '+shutil.which('curl')+' --disable --connect-to smtp.protonmail.ch:587:127.0.0.1:'+str(port)+' "$@" 2>'+str(root/'curl-erreur')+'\n');wrapper.chmod(0o700)
            def lit(s):return '"'+str(s).replace('\\','\\\\').replace('"','\\"')+'"'
            runner=root/'verifier.lisp';runner.write_text(f'''(load {lit(ROOT/'assemblage/charger.lisp')})
(asdf:load-system "mrjam-courriel")
(mrjam-native:initialiser-crypto {lit(os.environ.get('MRJAM_LIBCRYPTO','/lib/x86_64-linux-gnu/libcrypto.so.3'))})
(let* ((config (vision:parse-json "{{\\\"host\\\":\\\"smtp.protonmail.ch\\\",\\\"port\\\":587,\\\"username\\\":\\\"sender@example.test\\\",\\\"password\\\":\\\"SyntheseSMTP2026Token\\\",\\\"from_address\\\":\\\"sender@example.test\\\",\\\"starttls_required\\\":true,\\\"certificate_verification\\\":true}}"))
       (message (mrjam-courriel::message-mime "smtp:1" "sender@example.test" "alice@example.test" "Épreuve" "Synthétique" nil 1791676800)))
  (setf (uiop:getenv "MRJAM_CURL") {lit(wrapper)})
  (setf (uiop:getenv "MRJAM_CA_FILE") {lit(cert)})
  (mrjam-courriel::transmettre config message)
  (setf (uiop:getenv "MRJAM_CA_FILE") {lit('/etc/ssl/certs/ca-certificates.crt')})
  (assert (handler-case (progn (mrjam-courriel::transmettre config message) nil) (mrjam-courriel:courriel-error () t)))
  (setf (uiop:getenv "MRJAM_CA_FILE") {lit(cert)})
  (assert (handler-case (progn (mrjam-courriel::transmettre config message) nil) (mrjam-courriel:courriel-error () t)))
  (format t "STARTTLS vérifié ; certificat non approuvé refusé avant authentification.~%"))
''')
            try:
                subprocess.run([os.environ.get('SBCL','sbcl'),'--script',str(runner)],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            except subprocess.CalledProcessError:
                # Seulement le relais et credential synthétiques de cette fixture.
                raise AssertionError((root/'curl-erreur').read_text()[:1000]+str(state)) from None
            finally:server.shutdown();thread.join(timeout=5)
        assert state=={'auth_tls':1,'data':1,'auth_plain':0},state
        print('Un envoi synthétique sous TLS ; aucun secret transmis en clair, aucun relais externe contacté.')

if __name__=='__main__':verifier()
