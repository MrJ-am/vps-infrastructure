"""Véritable dialogue STARTTLS local : refus du certificat inconnu avant AUTH."""
import datetime
import importlib.util
from pathlib import Path
import queue
import smtplib
import socketserver
import ssl
import tempfile
import threading
import unittest
from unittest.mock import patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

spec=importlib.util.spec_from_file_location('courriel_tls',Path(__file__).resolve().parents[1]/'services/mrjam-courriel/courriel.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
CONFIG=dict(host='smtp.protonmail.ch',port=587,username='synthetique@example.test',
            password='JetonSynthetique123',from_address='synthetique@example.test',
            starttls_required=True,certificate_verification=True)


class Dialogue(socketserver.StreamRequestHandler):
    def finish(self):
        try:super().finish()
        finally:self.connection.close()

    def handle(self):
        self.connection.settimeout(5)
        self.wfile.write(b'220 localhost\r\n');tls=False;destinataire=False
        while ligne:=self.rfile.readline(8192):
            commande=ligne.decode('ascii',errors='replace').strip().upper()
            if commande.startswith('EHLO '):
                self.wfile.write(b'250-localhost\r\n250-AUTH PLAIN\r\n250 STARTTLS\r\n')
            elif commande=='STARTTLS':
                self.wfile.write(b'220 commencer TLS\r\n')
                try:self.connection=self.server.contexte.wrap_socket(self.connection,server_side=True)
                except ssl.SSLError:return
                self.rfile=self.connection.makefile('rb');self.wfile=self.connection.makefile('wb',buffering=0);tls=True
            elif commande.startswith('AUTH '):
                self.server.auth.put(tls);self.wfile.write(b'235 OK\r\n' if tls else b'530 TLS requis\r\n')
            elif commande.startswith('MAIL FROM:') and tls:self.wfile.write(b'250 OK\r\n')
            elif commande.startswith('RCPT TO:') and tls:
                destinataire=commande.endswith('@EXAMPLE.TEST>')
                self.wfile.write(b'250 OK\r\n' if destinataire else b'550 test uniquement\r\n')
            elif commande=='DATA' and destinataire:
                self.wfile.write(b'354 terminer par un point\r\n');donnees=bytearray()
                while (ligne:=self.rfile.readline(8192)) not in (b'.\r\n',b''):
                    donnees.extend(ligne)
                    if len(donnees)>65536:return
                self.server.messages.put(bytes(donnees));self.wfile.write(b'250 OK\r\n')
            elif commande=='QUIT':self.wfile.write(b'221 au revoir\r\n');return
            else:self.wfile.write(b'502 refus\r\n')


class CourrielTLS(unittest.TestCase):
    def test_certificat_obligatoire_auth_apres_tls_et_message_reel(self):
        with tempfile.TemporaryDirectory() as root:
            r=Path(root);key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
            nom=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'localhost')])
            maintenant=datetime.datetime.now(datetime.timezone.utc)
            cert=(x509.CertificateBuilder().subject_name(nom).issuer_name(nom).public_key(key.public_key())
                  .serial_number(x509.random_serial_number()).not_valid_before(maintenant-datetime.timedelta(minutes=1))
                  .not_valid_after(maintenant+datetime.timedelta(days=1))
                  .add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost')]),critical=False)
                  .sign(key,hashes.SHA256()))
            (r/'cert.pem').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
            (r/'cle.pem').write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
            contexte=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);contexte.load_cert_chain(r/'cert.pem',r/'cle.pem')
            serveur=socketserver.ThreadingTCPServer(('127.0.0.1',0),Dialogue)
            serveur.daemon_threads=True;serveur.contexte=contexte;serveur.auth=queue.Queue();serveur.messages=queue.Queue()
            threading.Thread(target=serveur.serve_forever,daemon=True).start()
            smtp_original=smtplib.SMTP;contexte_original=ssl.create_default_context
            def local(*_,**kwargs):return smtp_original('localhost',serveur.server_address[1],timeout=5)
            try:
                file=module.FileCourriel(r/'file.sqlite',CONFIG['from_address'])
                file.ajouter('test:tls','personne@example.test','Qualification','Courriel synthétique')
                with patch.object(module.smtplib,'SMTP',side_effect=local):file.traiter(CONFIG,100)
                self.assertTrue(serveur.auth.empty());self.assertTrue(serveur.messages.empty())
                self.assertEqual(file.etat('test:tls')['etat'],'attente')
                with patch.object(module.smtplib,'SMTP',side_effect=local), patch.object(module.ssl,'create_default_context',side_effect=lambda:contexte_original(cafile=r/'cert.pem')):
                    file.traiter(CONFIG,160)
                self.assertTrue(serveur.auth.get(timeout=5))
                self.assertIn(b'Qualification',serveur.messages.get(timeout=5))
                self.assertEqual(file.etat('test:tls')['etat'],'accepte_relais')
            finally:serveur.shutdown();serveur.server_close()


if __name__=='__main__':unittest.main()
