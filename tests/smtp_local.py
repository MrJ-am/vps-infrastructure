"""Relais de qualification isolé : uniquement des adresses example.test."""
from email.parser import BytesParser
from email.policy import default
import queue
import socketserver
import threading


class Relais(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, host='127.0.0.1', port=0):
        self.messages = queue.Queue()
        super().__init__((host, port), Dialogue)

    def demarrer(self):
        threading.Thread(target=self.serve_forever, daemon=True).start()
        return self


class Dialogue(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(15)
        self.wfile.write(b'220 qualification locale\r\n')
        destinataire = False
        while ligne := self.rfile.readline(8192):
            commande = ligne.decode('ascii', errors='replace').strip().upper()
            if commande.startswith(('EHLO ', 'HELO ')):
                reponse = b'250-localhost\r\n250 SIZE 1048576\r\n'
            elif commande.startswith('MAIL FROM:'):
                reponse = b'250 OK\r\n'
            elif commande.startswith('RCPT TO:'):
                destinataire = commande.endswith('@EXAMPLE.TEST>')
                reponse = b'250 OK\r\n' if destinataire else b'550 adresses de test uniquement\r\n'
            elif commande == 'DATA' and destinataire:
                self.wfile.write(b'354 terminer par un point\r\n')
                contenu = bytearray()
                while (ligne := self.rfile.readline(8192)) not in (b'.\r\n', b''):
                    contenu.extend(ligne[1:] if ligne.startswith(b'..') else ligne)
                    if len(contenu) > 1048576:
                        return
                self.server.messages.put(BytesParser(policy=default).parsebytes(contenu))
                reponse = b'250 accepte par le relais synthetique\r\n'
            elif commande == 'QUIT':
                self.wfile.write(b'221 au revoir\r\n')
                return
            elif commande in ('RSET', 'NOOP'):
                reponse = b'250 OK\r\n'
            else:
                reponse = b'502 commande indisponible\r\n'
            self.wfile.write(reponse)
