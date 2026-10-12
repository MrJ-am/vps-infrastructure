"""Fixture HTTPS synthétique pour le client Lisp, distincte de Kanidm réel."""
import base64
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import ssl
import subprocess
import sys
import tempfile
from threading import Thread
import time
from urllib.parse import parse_qs, unquote

SECRET = 'fixture-client-secret:+&%='


class Fixture:
    def __enter__(self):
        self.temp = tempfile.TemporaryDirectory(prefix='oidc-https-')
        self.root = Path(self.temp.name); self.root.chmod(0o700)
        self.calls = Counter(); self.errors = []; self.servers = []
        def openssl(*args):
            subprocess.run(['openssl', *map(str, args)], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        key = self.root/'cle.pem'; cert = self.root/'ca.pem'
        openssl('req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', key,
                '-out', cert, '-days', '1', '-subj', '/CN=log.mrj.am',
                '-addext', 'subjectAltName=DNS:log.mrj.am')
        badkey = self.root/'mauvaise-cle.pem'; badcert = self.root/'mauvaise-ca.pem'
        openssl('req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', badkey,
                '-out', badcert, '-days', '1', '-subj', '/CN=wrong.example.test',
                '-addext', 'subjectAltName=DNS:wrong.example.test')
        wrongkey = self.root/'hote-cle.pem'; request = self.root/'hote.csr'; wrongcert = self.root/'hote.pem'
        openssl('req', '-new', '-newkey', 'rsa:2048', '-nodes', '-keyout', wrongkey,
                '-out', request, '-subj', '/CN=wrong.example.test')
        ext = self.root/'extensions'; ext.write_text('subjectAltName=DNS:wrong.example.test\n')
        openssl('x509', '-req', '-in', request, '-CA', cert, '-CAkey', key, '-CAcreateserial',
                '-out', wrongcert, '-days', '1', '-extfile', ext)
        for path in self.root.iterdir():
            path.chmod(0o600)
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def reply(self, status, document, raw=None):
                body = json.dumps(document).encode() if raw is None else raw
                try:
                    self.send_response(status); self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', str(len(body)))
                    self.send_header('Cache-Control', 'no-store')
                    if status == 302:
                        self.send_header('Location', 'https://intrus.invalid/')
                    self.end_headers()
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError, ssl.SSLError):
                    pass

            def do_GET(self):
                fixture.calls[self.path] += 1
                issuer = 'https://log.mrj.am/oauth2/openid/mrjam-vision'
                if self.path == '/oauth2/openid/mrjam-vision/.well-known/openid-configuration':
                    self.reply(200, {'issuer': issuer, 'authorization_endpoint': 'https://log.mrj.am/ui/oauth2',
                                    'token_endpoint': 'https://log.mrj.am/oauth2/token', 'jwks_uri': issuer+'/public_key.jwk',
                                    'response_types_supported': ['code'], 'id_token_signing_alg_values_supported': ['ES256'],
                                    'code_challenge_methods_supported': ['S256'], 'token_endpoint_auth_methods_supported': ['client_secret_basic']})
                elif self.path == '/oauth2/openid/mrjam-vision/public_key.jwk':
                    self.reply(200, {'keys': []})
                else:
                    fixture.errors.append('endpoint_get_inattendu'); self.reply(404, {})

            def do_POST(self):
                body = self.rfile.read(int(self.headers['Content-Length'])).decode()
                fields = parse_qs(body, strict_parsing=True)
                code = fields.get('code', [''])[0]
                fixture.calls[code or self.path] += 1
                try:
                    authorization = self.headers.get('Authorization', '')
                    if self.path == '/oauth2/token':
                        assert authorization.startswith('Basic ')
                        name, secret = base64.b64decode(authorization[6:], validate=True).decode().split(':', 1)
                        assert unquote(name) == 'mrjam-vision' and unquote(secret) == SECRET
                    else:
                        assert self.path in ('/oauth2/token/introspect', '/oauth2/token/revoke')
                        assert not authorization  # Contrat officiel Kanidm, aucun secret inutile.
                    assert self.headers['Content-Type'] == 'application/x-www-form-urlencoded'
                    # Le vrai processus curl a reçu les paramètres par pipe.
                    args = subprocess.check_output(['ps', '-C', 'curl', '-o', 'args='], text=True)
                    assert SECRET not in args and 'fixture-refresh' not in args and 'code_verifier' not in args
                    if fields.get('grant_type') == ['authorization_code']:
                        assert fields['redirect_uri'] == ['https://vision.mrj.am/auth/retour']
                        assert fields['code_verifier'] == ['a'*43]
                except (AssertionError, ValueError, KeyError):
                    fixture.errors.append('parametres_ou_secret_non_conformes'); self.reply(400, {}); return
                if code == 'fixture-redirection':
                    self.reply(302, {}, raw=b'')
                elif code == 'fixture-json-invalide':
                    self.reply(200, {}, raw=b'[invalide')
                elif code == 'fixture-trop-long':
                    self.reply(200, {}, raw=b'{"secret":"'+b'x'*70000+b'"}')
                elif code == 'fixture-timeout':
                    time.sleep(12); self.reply(200, {})
                elif self.path == '/oauth2/token/introspect':
                    self.reply(200, {'active': fields['token'] == ['fixture-access']})
                elif self.path == '/oauth2/token/revoke':
                    self.reply(200, {}, raw=b'')
                elif self.path == '/oauth2/token':
                    self.reply(200, {'access_token': 'fixture-access', 'refresh_token': 'fixture-refresh', 'token_type': 'Bearer'})
                else:
                    fixture.errors.append('endpoint_post_inattendu'); self.reply(404, {})

        class Serveur(ThreadingHTTPServer):
            def handle_error(self, *_):
                # Fermeture attendue après refus TLS/limite/timeout du client.
                # Une autre erreur de fixture bloque toujours la qualification.
                if not isinstance(sys.exc_info()[1], (BrokenPipeError, ConnectionResetError, ssl.SSLError)):
                    fixture.errors.append('erreur_serveur_inattendue')

        def server(certificate, private_key):
            result = Serveur(('127.0.0.1', 0), Handler)
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.load_cert_chain(certificate, private_key)
            result.socket = context.wrap_socket(result.socket, server_side=True)
            Thread(target=result.serve_forever, daemon=True).start()
            self.servers.append(result)
            return result.server_port
        import shutil
        curl = os.environ.get('MRJAM_CURL') or shutil.which('curl')
        self.description = {'curl': curl, 'ca': str(cert), 'port': server(cert, key),
                            'mauvaise_ca': str(badcert), 'mauvais_port': server(wrongcert, wrongkey)}
        self.path = self.root/'fixture.json'
        self.path.write_text(json.dumps(self.description)); self.path.chmod(0o600)
        return self

    def verifier(self):
        assert not self.errors, self.errors
        for code in ('fixture-code', 'fixture-redirection', 'fixture-json-invalide', 'fixture-trop-long', 'fixture-timeout'):
            assert self.calls[code] == 1, 'Un POST sensible a été répété ou ignoré'
        assert self.calls['/oauth2/openid/mrjam-vision/.well-known/openid-configuration'] == 1, 'Échec TLS a envoyé une requête HTTP'
        assert self.calls['/oauth2/token/revoke'] == 1
        assert self.calls['/oauth2/token'] == 1
        assert self.calls['/oauth2/token/introspect'] == 2
        assert sum(self.calls.values()) == 11

    def __exit__(self, *_):
        for server in self.servers:
            server.shutdown(); server.server_close()
        self.temp.cleanup()
