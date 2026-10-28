"""Sessions communes mrj.am ; service privé derrière Nginx, sans données métier."""
import hashlib
import hmac
from http.cookies import SimpleCookie, CookieError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time
from contextlib import closing
from passlib.hash import sha512_crypt
import oauth

COOKIE = '__Secure-mrj_session'
LIFETIME = 12 * 60 * 60
IDLE = 2 * 60 * 60
DUREE_TOKEN_MCP = 365 * 24 * 60 * 60
NOM_TOKEN_DEFAUT = 'Mistral'

class Sessions:
    def __init__(self, path, credentials, domain, hosts):
        self.path, self.credentials, self.domain, self.hosts = str(path), Path(credentials), domain, set(hosts)
        self.dummy = sha512_crypt.using(rounds=5000).hash(secrets.token_urlsafe(32))
        with closing(self.connect()) as db, db:
            db.executescript('''CREATE TABLE IF NOT EXISTS sessions (
              digest TEXT PRIMARY KEY, username TEXT NOT NULL, csrf TEXT NOT NULL,
              expires INTEGER NOT NULL, last_seen INTEGER NOT NULL, fingerprint TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS attempts (ip TEXT NOT NULL, at INTEGER NOT NULL);
              CREATE INDEX IF NOT EXISTS attempts_ip ON attempts(ip,at);
              CREATE TABLE IF NOT EXISTS mcp_tokens (
                username TEXT PRIMARY KEY, digest TEXT NOT NULL UNIQUE,
                expires INTEGER NOT NULL, fingerprint TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS access_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL,
                name TEXT NOT NULL, digest TEXT NOT NULL UNIQUE,
                created INTEGER NOT NULL, expires INTEGER NOT NULL,
                revoked INTEGER, fingerprint TEXT NOT NULL);
              CREATE INDEX IF NOT EXISTS access_tokens_user
                ON access_tokens(username,created DESC);''')
            # Migration additive : le token historique Mistral garde exactement
            # son condensat et son expiration, donc reste utilisable.
            now = int(time.time())
            for row in db.execute('SELECT username,digest,expires,fingerprint FROM mcp_tokens').fetchall():
                if not db.execute('SELECT 1 FROM access_tokens WHERE digest=?', (row['digest'],)).fetchone():
                    db.execute('INSERT INTO access_tokens(username,name,digest,created,expires,revoked,fingerprint) VALUES (?,?,?,?,?,NULL,?)',
                               (row['username'], NOM_TOKEN_DEFAUT, row['digest'], now, row['expires'], row['fingerprint']))
        oauth.initialiser(self)
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        return db
    def fingerprint(self):
        return hashlib.sha256(self.credentials.read_bytes()).hexdigest()
    def login(self, username, password, ip):
        now = int(time.time())
        with closing(self.connect()) as db, db:
            db.execute('DELETE FROM attempts WHERE at < ?', (now-600,))
            db.execute('DELETE FROM sessions WHERE expires < ? OR last_seen < ?', (now,now-IDLE))
            if db.execute('SELECT count(*) FROM attempts WHERE ip=?', (ip,)).fetchone()[0] >= 10:
                return None, 'rate_limited'
            db.execute('INSERT INTO attempts VALUES (?,?)', (ip,now))
        content=self.credentials.read_bytes()
        fingerprint=hashlib.sha256(content).hexdigest()
        entries=dict(line.split(':',1) for line in content.decode().splitlines() if ':' in line)
        encoded=entries.get(username, self.dummy)
        # Les comptes de verrouillage et le fichier de test Mobile Live sont exclus.
        eligible=bool(re.fullmatch(r'[A-Za-z0-9_.-]{1,64}', username)) and not username.startswith(('vision-bootstrap-','vision-disabled'))
        try:
            valid=sha512_crypt.verify(password, encoded if encoded.startswith('$6$') else self.dummy)
        except (ValueError, TypeError):
            valid=False
        if not valid or not eligible or username not in entries:
            return None, 'invalid_credentials'
        token,csrf=secrets.token_urlsafe(32),secrets.token_urlsafe(32)
        with closing(self.connect()) as db, db:
            db.execute('DELETE FROM attempts WHERE ip=?', (ip,))
            # Bornage des sessions par compte ; aucune session privée dans les logs.
            db.execute('DELETE FROM sessions WHERE username=? AND digest NOT IN (SELECT digest FROM sessions WHERE username=? ORDER BY last_seen DESC LIMIT 19)', (username,username))
            db.execute('INSERT INTO sessions VALUES (?,?,?,?,?,?)', (hashlib.sha256(token.encode()).hexdigest(), username,csrf,now+LIFETIME,now,fingerprint))
        return {'token':token,'username':username,'csrf':csrf,'expiresAt':now+LIFETIME}, None
    def token(self, cookie):
        if sum(part.strip().startswith(COOKIE+'=') for part in cookie.split(';')) != 1:
            return None
        try:
            parsed=SimpleCookie();parsed.load(cookie)
            token=parsed[COOKIE].value
            return token if re.fullmatch(r'[A-Za-z0-9_-]{43}',token) else None
        except (CookieError,KeyError):
            return None
    def session(self,cookie):
        token=self.token(cookie)
        if not token:return None
        digest=hashlib.sha256(token.encode()).hexdigest();now=int(time.time())
        with closing(self.connect()) as db, db:
            row=db.execute('SELECT * FROM sessions WHERE digest=? AND expires>? AND last_seen>?', (digest,now,now-IDLE)).fetchone()
            if row is None or not hmac.compare_digest(row['fingerprint'],self.fingerprint()):return None
            db.execute('UPDATE sessions SET last_seen=? WHERE digest=?',(now,digest))
            return dict(row)
    def logout(self,cookie):
        token=self.token(cookie)
        if token:
            with closing(self.connect()) as db, db:
                db.execute('DELETE FROM sessions WHERE digest=?',(hashlib.sha256(token.encode()).hexdigest(),))
    def tokens_acces(self, username):
        """Historique des tokens d'un compte, sans jamais exposer leurs secrets."""
        now = int(time.time())
        empreinte = self.fingerprint()
        with closing(self.connect()) as db:
            lignes = db.execute(
                'SELECT id,name,created,expires,revoked,fingerprint FROM access_tokens WHERE username=? ORDER BY created DESC,id DESC',
                (username,)).fetchall()
        return {'tokens': [
            {'id': ligne['id'], 'name': ligne['name'], 'createdAt': ligne['created'],
             'expiresAt': ligne['expires'], 'revokedAt': ligne['revoked'],
             'active': ligne['revoked'] is None and ligne['expires'] > now
                       and hmac.compare_digest(ligne['fingerprint'], empreinte)}
            for ligne in lignes]}

    def creer_token_acces(self, username, name):
        nom = name.strip()
        if not 1 <= len(nom) <= 80 or any(ord(c) < 32 for c in nom):
            raise ValueError('invalid_token_name')
        secret = secrets.token_urlsafe(32)
        maintenant = int(time.time())
        expiration = maintenant + DUREE_TOKEN_MCP
        with closing(self.connect()) as db, db:
            curseur = db.execute(
                'INSERT INTO access_tokens(username,name,digest,created,expires,revoked,fingerprint) VALUES (?,?,?,?,?,NULL,?)',
                (username, nom, hashlib.sha256(secret.encode()).hexdigest(),
                 maintenant, expiration, self.fingerprint()))
            identifiant = curseur.lastrowid
        return {'token': secret, 'id': identifiant, 'name': nom,
                'createdAt': maintenant, 'expiresAt': expiration, 'active': True}

    def revoquer_token_acces(self, username, identifiant):
        maintenant = int(time.time())
        with closing(self.connect()) as db, db:
            curseur = db.execute(
                'UPDATE access_tokens SET revoked=? WHERE id=? AND username=? AND revoked IS NULL',
                (maintenant, identifiant, username))
        if curseur.rowcount != 1:
            raise ValueError('unknown_token')
        return self.tokens_acces(username)

    def token_mcp(self, username, creer=False, revoquer=False):
        """Compatibilité de l'ancienne API : agit seulement sur le token nommé Mistral."""
        with closing(self.connect()) as db:
            ligne = db.execute(
                'SELECT id FROM access_tokens WHERE username=? AND name=? AND revoked IS NULL ORDER BY id DESC LIMIT 1',
                (username, NOM_TOKEN_DEFAUT)).fetchone()
        if revoquer:
            if ligne:
                resultat = self.revoquer_token_acces(username, ligne['id'])
            else:
                resultat = {'active': False, 'expiresAt': None}
            with closing(self.connect()) as db, db:
                db.execute('DELETE FROM mcp_tokens WHERE username=?', (username,))
            return resultat
        if creer:
            if ligne:
                self.revoquer_token_acces(username, ligne['id'])
            cree = self.creer_token_acces(username, NOM_TOKEN_DEFAUT)
            with closing(self.connect()) as db, db:
                db.execute('DELETE FROM mcp_tokens WHERE username=?', (username,))
                db.execute('INSERT INTO mcp_tokens VALUES (?,?,?,?)',
                           (username, hashlib.sha256(cree['token'].encode()).hexdigest(),
                            cree['expiresAt'], self.fingerprint()))
            return {'token': cree['token'], 'expiresAt': cree['expiresAt']}
        historique = self.tokens_acces(username)['tokens']
        mistral = next((t for t in historique if t['name'] == NOM_TOKEN_DEFAUT and t['active']), None)
        return {'active': bool(mistral), 'expiresAt': mistral['expiresAt'] if mistral else None}

    def verifier_token_mcp(self, authorization):
        utilisateur_oauth = oauth.verifier(self, authorization)
        if utilisateur_oauth:
            return utilisateur_oauth
        correspondance = re.fullmatch(r'Bearer ([A-Za-z0-9_-]{43})', authorization, re.IGNORECASE)
        if not correspondance:
            return None
        condensat = hashlib.sha256(correspondance[1].encode()).hexdigest()
        maintenant = int(time.time())
        with closing(self.connect()) as db:
            ligne = db.execute('SELECT * FROM access_tokens WHERE digest=?', (condensat,)).fetchone()
            if ligne is not None:
                if (ligne['revoked'] is None and ligne['expires'] > maintenant
                        and hmac.compare_digest(ligne['fingerprint'], self.fingerprint())):
                    return ligne['username']
                return None
            # Repli de sûreté uniquement pour une base antérieure à la migration.
            ligne = db.execute('SELECT * FROM mcp_tokens WHERE digest=? AND expires>?',
                               (condensat, maintenant)).fetchone()
        if ligne and hmac.compare_digest(ligne['fingerprint'], self.fingerprint()):
            return ligne['username']
        return None
    def cookie(self,token='',clear=False):
        return f'{COOKIE}={token}; Domain={self.domain}; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age={0 if clear else LIFETIME}'

class Handler(BaseHTTPRequestHandler):
    server_version = 'mrj-auth'
    def log_message(self,*args):pass
    def setup(self):
        super().setup();self.connection.settimeout(10)
    def reply(self,status,payload=None,headers=None):
        data=json.dumps(payload,ensure_ascii=False).encode() if payload is not None else b''
        self.send_response(status)
        for k,v in {'Content-Type':'application/json; charset=utf-8','Content-Length':str(len(data)), 'Cache-Control':'no-store','X-Content-Type-Options':'nosniff',**(headers or {})}.items():self.send_header(k,v)
        self.end_headers();self.wfile.write(data)
    def dispatch(self):
        app=self.server.sessions
        host=self.headers.get('X-Forwarded-Host','')
        if host not in app.hosts or self.headers.get('X-Forwarded-Proto')!='https':
            return self.reply(403,{'error':'invalid_origin'})
        if oauth.traiter(self, app, host):
            return
        if self.path == '/verify-mcp' and self.command == 'GET':
            valeurs = self.headers.get_all('Authorization', [])
            utilisateur = (app.verifier_token_mcp(valeurs[0])
                           if len(valeurs) == 1 and host == 'vision.mrj.am' else None)
            if not utilisateur:
                return self.reply(401, {'error': 'authentication_required'},
                                  {'WWW-Authenticate': 'Bearer realm="Vision MCP", resource_metadata="https://vision.mrj.am/.well-known/oauth-protected-resource/mcp"'})
            return self.reply(204, headers={'X-Mrj-User': utilisateur})
        if self.path in ('/auth/mcp', '/auth/mcp.js', '/auth/style.css') and self.command == 'GET':
            fichier = {'/auth/mcp': 'mcp.html', '/auth/mcp.js': 'mcp.js',
                       '/auth/style.css': 'style.css'}[self.path]
            donnees = Path(__file__).with_name(fichier).read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8' if fichier.endswith('.html')
                             else 'text/css; charset=utf-8' if fichier.endswith('.css')
                             else 'text/javascript; charset=utf-8')
            self.send_header('Content-Length', str(len(donnees)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(donnees)
            return
        session=app.session(self.headers.get('Cookie',''))
        if self.path in ('/auth/mcp-token', '/auth/access-tokens'):
            if host != 'vision.mrj.am':
                return self.reply(403, {'error': 'invalid_origin'})
            if not session:
                return self.reply(401, {'error': 'authentication_required'})
            if self.command == 'GET':
                return self.reply(200, app.token_mcp(session['username'])
                                  if self.path == '/auth/mcp-token'
                                  else app.tokens_acces(session['username']))
        if self.path=='/verify' and self.command=='GET':
            if not session:return self.reply(401,{'error':'authentication_required'})
            if self.headers.get('X-Original-Method') not in ('GET','HEAD'):
                if self.headers.get('Origin')!='https://'+host or not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),session['csrf']):
                    return self.reply(403,{'error':'csrf_required'})
            return self.reply(204,headers={'X-Mrj-User':session['username']})
        if self.path=='/auth/session' and self.command=='GET':
            if not session:return self.reply(401,{'error':'authentication_required'})
            return self.reply(200,{'username':session['username'],'csrf':session['csrf'],'expiresAt':session['expires']})
        if self.path not in ('/auth/login','/auth/logout','/auth/mcp-token','/auth/access-tokens') or self.command!='POST':
            return self.reply(404,{'error':'not_found'})
        if self.headers.get('Origin')!='https://'+host:
            return self.reply(403,{'error':'invalid_origin'})
        if self.headers.get('Content-Type','').split(';')[0].strip()!='application/json' or self.headers.get('Transfer-Encoding'):
            return self.reply(415,{'error':'json_required'})
        length=int(self.headers.get('Content-Length','0'))
        if not 0 < length <= 8192:return self.reply(413,{'error':'invalid_input'})
        body=json.loads(self.rfile.read(length))
        if not isinstance(body,dict):return self.reply(400,{'error':'invalid_input'})
        if self.path in ('/auth/mcp-token', '/auth/access-tokens'):
            if not hmac.compare_digest(self.headers.get('X-CSRF-Token',''), session['csrf']):
                return self.reply(403, {'error': 'csrf_required'})
            if self.path == '/auth/mcp-token':
                if set(body) != {'action'} or body['action'] not in ('creer', 'revoquer'):
                    return self.reply(400, {'error': 'invalid_input'})
                return self.reply(200, app.token_mcp(session['username'],
                                  creer=body['action'] == 'creer', revoquer=body['action'] == 'revoquer'))
            action = body.get('action')
            if action == 'creer' and set(body) == {'action','name'} and isinstance(body['name'], str):
                return self.reply(200, app.creer_token_acces(session['username'], body['name']))
            if action == 'revoquer' and set(body) == {'action','id'} and isinstance(body['id'], int):
                return self.reply(200, app.revoquer_token_acces(session['username'], body['id']))
            return self.reply(400, {'error': 'invalid_input'})
        if self.path=='/auth/logout':
            if not session:return self.reply(401,{'error':'authentication_required'})
            if not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),session['csrf']):return self.reply(403,{'error':'csrf_required'})
            app.logout(self.headers.get('Cookie',''))
            return self.reply(200,{'signedOut':True}, {'Set-Cookie':app.cookie(clear=True)})
        if set(body)!={'username','password'} or not isinstance(body['username'],str) or not isinstance(body['password'],str) or len(body['username'])>64 or not 1<=len(body['password'])<=1024:
            return self.reply(400,{'error':'invalid_input'})
        result,error=app.login(body['username'],body['password'],self.headers.get('X-Real-IP','unknown'))
        if error:return self.reply(429 if error=='rate_limited' else 401,{'error':error})
        app.logout(self.headers.get('Cookie',''))
        token=result.pop('token')
        return self.reply(200,result,{'Set-Cookie':app.cookie(token)})
    def handle_method(self):
        try:self.dispatch()
        except (ValueError,UnicodeError):self.reply(400,{'error':'invalid_input'})
        except (OSError,sqlite3.Error):self.reply(503,{'error':'unavailable'})
    do_GET=handle_method
    do_POST=handle_method

if __name__=='__main__':
    os.umask(0o077)
    if os.environ.get('MRJ_AUTH_MODE')=='oidc':
        from oidc import HandlerOIDC,creer_sessions
        import threading
        server=ThreadingHTTPServer(('127.0.0.1',int(os.environ.get('MRJ_AUTH_PORT','3002'))),HandlerOIDC)
        server.sessions=creer_sessions()
        def nettoyer_periodiquement():
            while True:
                try:server.sessions.nettoyer_effacements()
                except Exception:pass
                time.sleep(3600)
        threading.Thread(target=nettoyer_periodiquement,daemon=True).start()
    else:
        server=ThreadingHTTPServer(('127.0.0.1',int(os.environ.get('MRJ_AUTH_PORT','3002'))),Handler)
        server.sessions=Sessions(os.environ['MRJ_AUTH_DATABASE'],os.environ['MRJ_AUTH_CREDENTIALS'],os.environ['MRJ_AUTH_DOMAIN'],os.environ['MRJ_AUTH_HOSTS'].split(','))
    server.serve_forever()
