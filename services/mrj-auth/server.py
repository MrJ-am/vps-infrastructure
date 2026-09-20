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

COOKIE = '__Secure-mrj_session'
LIFETIME = 12 * 60 * 60
IDLE = 2 * 60 * 60

class Sessions:
    def __init__(self, path, credentials, domain, hosts):
        self.path, self.credentials, self.domain, self.hosts = str(path), Path(credentials), domain, set(hosts)
        self.dummy = sha512_crypt.using(rounds=5000).hash(secrets.token_urlsafe(32))
        with closing(self.connect()) as db, db:
            db.executescript('''CREATE TABLE IF NOT EXISTS sessions (
              digest TEXT PRIMARY KEY, username TEXT NOT NULL, csrf TEXT NOT NULL,
              expires INTEGER NOT NULL, last_seen INTEGER NOT NULL, fingerprint TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS attempts (ip TEXT NOT NULL, at INTEGER NOT NULL);
              CREATE INDEX IF NOT EXISTS attempts_ip ON attempts(ip,at);''')
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
        session=app.session(self.headers.get('Cookie',''))
        if self.path=='/verify' and self.command=='GET':
            if not session:return self.reply(401,{'error':'authentication_required'})
            if self.headers.get('X-Original-Method') not in ('GET','HEAD'):
                if self.headers.get('Origin')!='https://'+host or not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),session['csrf']):
                    return self.reply(403,{'error':'csrf_required'})
            return self.reply(204,headers={'X-Mrj-User':session['username']})
        if self.path=='/auth/session' and self.command=='GET':
            if not session:return self.reply(401,{'error':'authentication_required'})
            return self.reply(200,{'username':session['username'],'csrf':session['csrf'],'expiresAt':session['expires']})
        if self.path not in ('/auth/login','/auth/logout') or self.command!='POST':
            return self.reply(404,{'error':'not_found'})
        if self.headers.get('Origin')!='https://'+host:
            return self.reply(403,{'error':'invalid_origin'})
        if self.headers.get('Content-Type','').split(';')[0].strip()!='application/json' or self.headers.get('Transfer-Encoding'):
            return self.reply(415,{'error':'json_required'})
        length=int(self.headers.get('Content-Length','0'))
        if not 0 < length <= 8192:return self.reply(413,{'error':'invalid_input'})
        body=json.loads(self.rfile.read(length))
        if not isinstance(body,dict):return self.reply(400,{'error':'invalid_input'})
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
    server=ThreadingHTTPServer(('127.0.0.1',int(os.environ.get('MRJ_AUTH_PORT','3002'))),Handler)
    server.sessions=Sessions(os.environ['MRJ_AUTH_DATABASE'],os.environ['MRJ_AUTH_CREDENTIALS'],os.environ['MRJ_AUTH_DOMAIN'],os.environ['MRJ_AUTH_HOSTS'].split(','))
    server.serve_forever()
