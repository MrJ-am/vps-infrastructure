"""TLS/navigateur → vrai HTTP SBCL → SQLite → OIDC signé → MCP réel.

Le fournisseur OIDC et la page de retour ChatGPT sont des doubles explicites.
Toutes les connexions restent sur loopback, y compris CONNECT. Les erreurs de
session, rotations, PKCE, CSRF et décisions sont traitées par le code livré.
Cette suite ne qualifie ni Kanidm réel ni l'application propriétaire ChatGPT.
"""
import base64
from collections import Counter
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import secrets
import select
import shutil
import socket
from socketserver import StreamRequestHandler, ThreadingTCPServer
import sqlite3
import ssl
import subprocess
import tempfile
import threading
import time
from urllib.parse import parse_qs, urlencode, urlsplit

ROOT = Path(__file__).resolve().parents[1]
VISION = 'https://vision.mrj.am'
LOG = 'https://log.mrj.am'
CALLBACK = 'https://chatgpt.com/connector_platform_oauth_redirect'
ISSUER = LOG + '/oauth2/openid/mrjam-vision'


def b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()


def challenge(secret):
    return b64(hashlib.sha256(secret.encode()).digest())


class UnixHTTP(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__('localhost', timeout=15)
        self.path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(str(self.path))


class Fixture:
    def __init__(self, vision, *, sbcl='sbcl'):
        self.vision = Path(vision).resolve()
        if not (self.vision/'app.js').is_file():
            raise RuntimeError('Interface Vision compilée requise ; aucun double de consentement.')
        self.sbcl = sbcl
        self.temp = tempfile.TemporaryDirectory(prefix='mcp-reconnexion-')
        self.root = Path(self.temp.name)
        self.root.chmod(0o700)
        self.db = self.root/'sessions.sqlite'
        self.socket = self.root/'metier.sock'
        self.ca = self.root/'cert.pem'
        self.key = self.root/'tls.pem'
        self.signature = self.root/'signature.pem'
        self.errors = []
        self.calls = Counter()
        self.codes = {}
        self.access = {}
        self.refresh = {}
        self.pending = {}
        self.faults = {}
        self.drop_consent = False
        self.lock = threading.RLock()
        self.process = None
        self.callbacks = []
        self._openssl('req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', self.key,
            '-out', self.ca, '-days', '1', '-subj', '/CN=log.mrj.am', '-addext',
            'subjectAltName=DNS:log.mrj.am,DNS:vision.mrj.am,DNS:chatgpt.com,IP:127.0.0.1')
        self._openssl('ecparam', '-name', 'prime256v1', '-genkey', '-noout', '-out', self.signature)
        public = self._openssl('ec', '-in', self.signature, '-pubout', '-outform', 'DER')[-65:]
        assert public[0] == 4
        self.jwks = {'keys': [{'kty': 'EC', 'crv': 'P-256', 'use': 'sig', 'alg': 'ES256',
                               'kid': 'fixture', 'x': b64(public[1:33]), 'y': b64(public[33:])}]}
        for path in self.root.iterdir():
            path.chmod(0o600)

    def _openssl(self, *args, data=None):
        return subprocess.run(['openssl', *map(str,args)], input=data, check=True,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout

    def jwt(self, claims):
        message = (b64(json.dumps({'alg': 'ES256', 'kid': 'fixture', 'typ': 'JWT'}).encode())+'.'+
                   b64(json.dumps(claims).encode())).encode()
        der = self._openssl('dgst', '-sha256', '-sign', self.signature, data=message)
        # Signature ECDSA DER produite par OpenSSL : deux INTEGER, <= 72 octets.
        assert der[0] == 48 and der[1] == len(der)-2 and der[2] == 2
        pos = 4+der[3]
        assert der[pos] == 2 and pos+2+der[pos+1] == len(der)
        r = int.from_bytes(der[4:pos], 'big').to_bytes(32, 'big')
        s = int.from_bytes(der[pos+2:], 'big').to_bytes(32, 'big')
        return message.decode()+'.'+b64(r+s)

    def tokens(self, record):
        access = secrets.token_urlsafe(32)
        refresh = secrets.token_urlsafe(32)
        now = int(time.time())
        self.access[access] = dict(record, active=True, exp=now+3600)
        self.refresh[refresh] = record.copy()
        claims = dict(iss=ISSUER, sub=record['subject'], aud='mrjam-vision', nonce=record['nonce'],
                      iat=now, exp=now+3600, auth_time=now, at_hash=b64(hashlib.sha256(access.encode()).digest()[:16]))
        return {'access_token': access, 'refresh_token': refresh, 'id_token': self.jwt(claims),
                'token_type': 'Bearer', 'expires_in': 3600}

    def oidc(self, method, path, headers, body):
        if method == 'GET' and path == '/oauth2/openid/mrjam-vision/public_key.jwk':
            return 200, self.jwks
        fields = {k:v[0] for k,v in parse_qs(body.decode(), keep_blank_values=True).items()}
        if method != 'POST':
            raise AssertionError('Méthode fournisseur inattendue')
        with self.lock:
            self.calls[path] += 1
            if path in self.faults:
                return self.faults[path]
            if path == '/oauth2/token/introspect':
                record = self.access.get(fields.get('token'))
                return 200, {'active': bool(record and record['active']), 'exp': record['exp'] if record else 0}
            if path == '/oauth2/token/revoke':
                self.refresh.pop(fields.get('token'), None)
                return 200, {}
            assert path == '/oauth2/token'
            assert headers.get('Authorization') == 'Basic '+base64.b64encode(b'mrjam-vision:secret-oidc-synthetique').decode()
            if fields.get('grant_type') == 'authorization_code':
                record = self.codes.pop(fields.get('code'), None)
                if not record or fields.get('redirect_uri') != VISION+'/auth/retour' or challenge(fields.get('code_verifier','')) != record['challenge']:
                    return 400, {'error': 'invalid_grant'}
            else:
                assert fields.get('grant_type') == 'refresh_token'
                record = self.refresh.pop(fields.get('refresh_token'), None)
                if not record:
                    return 400, {'error': 'invalid_grant'}
            return 200, self.tokens(record)

    def native_return(self, query, account):
        p = {k:v[0] for k,v in parse_qs(query).items()}
        assert p['client_id'] == 'mrjam-vision' and p['redirect_uri'] == VISION+'/auth/retour'
        assert p['response_type'] == 'code' and p['code_challenge_method'] == 'S256'
        code = secrets.token_urlsafe(32)
        self.codes[code] = {'nonce':p['nonce'], 'challenge':p['code_challenge'],
                           'subject':'00000000-0000-4000-8000-00000000000'+('1' if account=='alice' else '2')}
        return VISION+'/auth/retour?'+urlencode(dict(state=p['state'],code=code))

    def backend(self, method, path, body=b'', headers=None, *, service='log'):
        # Même frontière que le proxy déployé : ne jamais reprendre une identité
        # ou un en-tête interne fourni par le navigateur.
        allowed = {'content-type','cookie','origin','authorization','x-csrf-token','accept'}
        h = {k:v for k,v in (headers or {}).items() if k.lower() in allowed}
        h.update({'X-Forwarded-Host':'vision.mrj.am','X-Forwarded-Proto':'https',
                  'X-Mrjam-Service':service,'X-Original-Method':method})
        if service == 'vision':
            code, hs, _ = self.backend('GET','/verify-mcp', headers=headers)
            if code != 204:
                return code, hs, b'{"error":"authentication_required"}'
            user = next(v for k,v in hs if k.lower() == 'x-mrj-user')
            h.update({'X-Mrj-User':user,'X-Vision-Authenticated':'1'})
        conn = UnixHTTP(self.socket)
        try:
            conn.request(method,path,body,headers=h)
            r = conn.getresponse()
            return r.status, r.getheaders(), r.read()
        finally:
            conn.close()

    def __enter__(self):
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_GET(self): self.checked()
            def do_POST(self): self.checked()
            def send(self, status, body=b'', headers=()):
                if isinstance(body,dict):
                    body = json.dumps(body).encode(); headers = [*headers,('Content-Type','application/json')]
                self.send_response(status)
                for k,v in headers:
                    if k.lower() not in ('content-length','connection','transfer-encoding'):
                        self.send_header(k,v)
                self.send_header('Content-Length',str(len(body)))
                self.send_header('Cache-Control','no-store')
                self.end_headers(); self.wfile.write(body)
            def checked(self):
                try: self.dispatch()
                except (BrokenPipeError,ConnectionResetError,ssl.SSLEOFError): pass
                except Exception as e:
                    owner.errors.append(type(e).__name__)
                    self.send(502,{'error':'fixture_refusee'})
            def dispatch(self):
                host = self.headers.get('Host','').split(':')[0]
                p = urlsplit(self.path)
                body = self.rfile.read(int(self.headers.get('Content-Length','0')))
                if host == 'log.mrj.am':
                    if p.path in ('/ui/oauth2','/fixture-login'):
                        owner.calls[p.path] += 1
                    if p.path.startswith('/oauth2/'):
                        status, document = owner.oidc(self.command,p.path,self.headers,body)
                        return self.send(status,document)
                    if self.command == 'GET' and p.path == '/ui/oauth2':
                        account = next((part.split('=',1)[1] for part in self.headers.get('Cookie','').split('; ')
                                        if part.startswith('fixture_native=')),None)
                        if account in ('alice','bob'):
                            return self.send(302,headers=[('Location',owner.native_return(p.query,account))])
                        key = secrets.token_urlsafe(24); owner.pending[key] = p.query
                        # Écran fournisseur synthétique, pas une copie de l'UI Log.
                        page = ('<!doctype html><html lang="fr"><meta charset="utf-8"><title>Fournisseur de test isolé</title>'
                                '<form method="post" action="/fixture-login"><input name="demande" type="hidden" value="'+key+'">'
                                '<button name="compte" value="alice">Connexion Alice de test</button>'
                                '<button name="compte" value="bob">Connexion Bob de test</button></form></html>')
                        return self.send(200,page.encode(),[('Content-Type','text/html; charset=utf-8')])
                    if self.command == 'POST' and p.path == '/fixture-login':
                        fields = parse_qs(body.decode()); account = fields['compte'][0]
                        assert account in ('alice','bob')
                        target = owner.native_return(owner.pending.pop(fields['demande'][0]),account)
                        return self.send(302,headers=[('Location',target),('Set-Cookie','fixture_native='+account+'; Path=/; Secure; HttpOnly; SameSite=Lax')])
                if host == 'chatgpt.com' and p.path == urlsplit(CALLBACK).path:
                    owner.callbacks.append(parse_qs(p.query))
                    return self.send(200,b'Retour client de test', [('Content-Type','text/plain')])
                if host == 'vision.mrj.am':
                    if p.path.startswith(('/auth/','/oauth/','/.well-known/')) or p.path == '/mcp':
                        owner.calls[p.path] += 1
                        code, hs, data = owner.backend(self.command,self.path,body,dict(self.headers),
                                                      service='vision' if p.path == '/mcp' else 'log')
                        if p.path == '/auth/oauth-consentement' and owner.drop_consent:
                            owner.drop_consent = False
                            self.connection.shutdown(socket.SHUT_RDWR); self.connection.close(); return
                        return self.send(code,data,hs)
                    if self.command == 'GET':
                        f = (owner.vision/(p.path.lstrip('/') or 'app.html')).resolve()
                        if f.is_relative_to(owner.vision) and f.is_file():
                            return self.send(200,f.read_bytes(),[('Content-Type',mimetypes.guess_type(f.name)[0] or 'application/octet-stream')])
                self.send(404,{'error':'route_fixture_absente'})

        self.server = ThreadingHTTPServer(('127.0.0.1',0), Handler)
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.load_cert_chain(self.ca,self.key)
        self.server.socket = tls.wrap_socket(self.server.socket,server_side=True)
        self.port = self.server.server_port
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
        class Connect(StreamRequestHandler):
            def handle(self):
                line = self.rfile.readline(4096).decode().split()
                if len(line)!=3 or line[0]!='CONNECT' or line[1] not in ('log.mrj.am:443','vision.mrj.am:443','chatgpt.com:443'):
                    self.wfile.write(b'HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n'); return
                for _ in range(100):
                    header = self.rfile.readline(8192)
                    if not header: return
                    if header == b'\r\n': break
                else: return
                with socket.create_connection(('127.0.0.1',owner.port),timeout=15) as upstream:
                    self.wfile.write(b'HTTP/1.1 200 Connection established\r\n\r\n');self.wfile.flush()
                    peers = [self.connection,upstream]
                    try:
                        while True:
                            readable,_,_ = select.select(peers,[],[],15)
                            if not readable: return
                            for sock in readable:
                                data = sock.recv(65536)
                                if not data: return
                                (upstream if sock is self.connection else self.connection).sendall(data)
                    except (OSError,ConnectionError): return
        class Proxy(ThreadingTCPServer): daemon_threads=True
        self.proxy = Proxy(('127.0.0.1',0),Connect)
        threading.Thread(target=self.proxy.serve_forever,daemon=True).start()
        self.proxy_url = 'http://127.0.0.1:'+str(self.proxy.server_address[1])
        self.parameters = dict(curl=os.environ.get('MRJAM_CURL') or shutil.which('curl'),ca=str(self.ca),
            port=self.port,base=str(self.db),socket=str(self.socket),vision=str(self.vision),alice=True,bob=True)
        self.config = self.root/'fixture.json'
        self.config.write_text(json.dumps(self.parameters));self.config.chmod(0o600)
        self.start()
        return self

    def start(self):
        self.log = (self.root/'sbcl.log').open('ab')
        env = dict(os.environ,MRJAM_RECONNEXION_FIXTURE=str(self.config))
        self.process = subprocess.Popen([self.sbcl,'--script',str(ROOT/'tests/mcp-reconnexion-serveur.lisp')],
                                        cwd=ROOT,env=env,stdout=self.log,stderr=self.log)
        deadline = time.monotonic()+45
        while not self.socket.exists():
            if self.process.poll() is not None or time.monotonic()>deadline:
                raise RuntimeError('Le vrai serveur SBCL de test n’a pas démarré ; diagnostic privé : '+str(self.root/'sbcl.log'))
            time.sleep(.05)

    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try: self.process.wait(timeout=10)
            except subprocess.TimeoutExpired: self.process.kill();self.process.wait()
        if hasattr(self,'log'): self.log.close()
        self.socket.unlink(missing_ok=True)  # Uniquement notre répertoire éphémère après arrêt.

    def request(self, method, path, data=None, *, cookies=None, csrf=None, origin=VISION, bearer=None):
        headers = {'Host':'vision.mrj.am'}
        if data is None: body=b''
        elif isinstance(data,dict): body=json.dumps(data).encode();headers['Content-Type']='application/json'
        else: body=data.encode();headers['Content-Type']='application/x-www-form-urlencoded'
        if cookies: headers['Cookie']=cookies
        if csrf: headers['X-CSRF-Token']=csrf
        if origin: headers['Origin']=origin
        if bearer: headers['Authorization']='Bearer '+bearer
        conn=http.client.HTTPSConnection('127.0.0.1',self.port,context=ssl.create_default_context(cafile=str(self.ca)),timeout=20)
        try:
            conn.request(method,path,body,headers)
            response=conn.getresponse();raw=response.read();hs=response.getheaders()
            return response.status, hs, json.loads(raw) if raw and raw.startswith(b'{') else raw
        finally: conn.close()

    def register(self):
        code,_,d=self.request('POST','/oauth/register',{'client_name':'ChatGPT de test','redirect_uris':[CALLBACK]})
        assert code==201
        return d['client_id']

    def authorization(self, client, *, scope=True, state=None):
        verifier=secrets.token_urlsafe(32)
        params=dict(client_id=client,redirect_uri=CALLBACK,response_type='code',state=state or secrets.token_urlsafe(32),
                    code_challenge=challenge(verifier),code_challenge_method='S256',resource=VISION+'/mcp')
        if scope:params['scope']='vision:mcp'
        return VISION+'/oauth/authorize?'+urlencode(params),verifier,params['state']

    def exchange(self, client, code, verifier):
        return self.request('POST','/oauth/token',urlencode(dict(grant_type='authorization_code',client_id=client,
            code=code,redirect_uri=CALLBACK,code_verifier=verifier,resource=VISION+'/mcp')))

    def sql(self, statement, parameters=()):
        with sqlite3.connect(self.db) as db:
            db.row_factory=sqlite3.Row
            return [dict(r) for r in db.execute(statement,parameters)]

    def invalidate_native(self, *, revoked=True):
        for record in self.access.values():record['active']=False
        if revoked:self.refresh.clear()

    def __exit__(self,*args):
        self.stop()
        for name in ('proxy','server'):
            server=getattr(self,name,None)
            if server:server.shutdown();server.server_close()
        self.temp.cleanup()
