"""OIDC serveur : identité commune, cookies propres à chaque outil.

Authlib valide les jetons. Aucune API d'administration du fournisseur
d'identité n'est utilisée ou accordée aux administrateurs Vision.
"""
from contextlib import closing
import hashlib
import base64
import binascii
import hmac
from http.cookies import SimpleCookie, CookieError
import json
import os
from pathlib import Path
import re
import secrets
import time
from urllib.parse import parse_qs, urlsplit

from authlib.integrations.requests_client import OAuth2Session
from authlib.jose import JsonWebToken
from authlib.oidc.core import CodeIDToken
import psycopg
import requests

from server import Sessions, Handler, LIFETIME, IDLE
import oauth

COOKIE='__Host-mrj_session'
STATE_COOKIE='__Host-mrj_oidc'

def digest(value): return hashlib.sha256(value.encode()).hexdigest()

def cookie_token(header,name):
    if sum(p.strip().startswith(name+'=') for p in header.split(';'))!=1: return None
    try:
        p=SimpleCookie();p.load(header);v=p[name].value
        return v if re.fullmatch(r'[A-Za-z0-9_-]{43}',v) else None
    except (CookieError,KeyError): return None

def retour_valide(value):
    return (value in ('/','/auth/mcp','/#administration','/#compte') or
            value.startswith('/oauth/authorize?')) and len(value)<=4096 and not any(ord(c)<32 for c in value)

class Identites:
    def __init__(self,dsn): self.dsn=dsn
    def appeler(self,fonction,*args):
        # Identificateurs constants ; toutes les valeurs sont liées par psycopg.
        sql={'identifier':'SELECT vision_gestion.identifier(%s,%s)',
             'activer':'SELECT vision_gestion.activer(%s,%s,%s,%s,%s)',
             'apercu_invitation':'SELECT vision_gestion.apercu_invitation(%s)',
             'notice':'SELECT vision_gestion.notice()'}[fonction]
        with psycopg.connect(self.dsn) as db: return db.execute(sql,args).fetchone()[0]

class SessionsOIDC(Sessions):
    def __init__(self,path,credentials,domain,hosts,issuer,backend,client_id,secret_file,identites):
        super().__init__(path,credentials,domain,hosts)
        if not issuer.startswith('https://') or urlsplit(issuer).query or urlsplit(issuer).fragment:
            raise ValueError('issuer_invalide')
        if not backend.startswith('http://127.0.0.1:'): raise ValueError('backend_invalide')
        self.issuer,self.backend,self.client_id=issuer.rstrip('/'),backend.rstrip('/'),client_id
        self.secret_file=Path(secret_file);self.identites=identites
        with closing(self.connect()) as db,db:
            cols={r['name'] for r in db.execute('PRAGMA table_info(sessions)')}
            for nom in ('host','issuer','subject','auth_time','amr','sid'):
                if nom not in cols: db.execute('ALTER TABLE sessions ADD COLUMN '+nom+" TEXT NOT NULL DEFAULT ''")
            db.executescript('''CREATE TABLE IF NOT EXISTS oidc_transactions(
              state TEXT PRIMARY KEY, binding TEXT NOT NULL, host TEXT NOT NULL,
              verifier TEXT NOT NULL, nonce TEXT NOT NULL, retour TEXT NOT NULL,
              invitation TEXT, notice TEXT, expires INTEGER NOT NULL);
              CREATE TABLE IF NOT EXISTS oidc_principals(
              username TEXT PRIMARY KEY, issuer TEXT NOT NULL, subject TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS oidc_logout_replays(jti TEXT PRIMARY KEY, expires INTEGER NOT NULL);''')

    def client(self,host):
        return OAuth2Session(self.client_id,self.secret_file.read_text().strip(),
            scope='openid',redirect_uri='https://'+host+'/auth/retour',code_challenge_method='S256')

    def demarrer(self,host,retour='/',stepup=False,invitation=None,notice=None):
        if host not in self.hosts or not retour_valide(retour): raise ValueError('retour_invalide')
        verifier,nonce,binding=secrets.token_urlsafe(48),secrets.token_urlsafe(32),secrets.token_urlsafe(32)
        params={'nonce':nonce,'code_verifier':verifier}
        if stepup: params.update(prompt='login',max_age=0)
        url,state=self.client(host).create_authorization_url(self.issuer+'/protocol/openid-connect/auth',**params)
        with closing(self.connect()) as db,db:
            db.execute('DELETE FROM oidc_transactions WHERE expires<?',(int(time.time()),))
            db.execute('INSERT INTO oidc_transactions VALUES(?,?,?,?,?,?,?,?,?)',
              (digest(state),digest(binding),host,verifier,nonce,retour,invitation,notice,int(time.time())+600))
        return url,binding

    def terminer(self,host,state,code,cookie):
        binding=cookie_token(cookie,STATE_COOKIE)
        if not binding: raise ValueError('etat_invalide')
        with closing(self.connect()) as db,db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM oidc_transactions WHERE state=?',(digest(state),)).fetchone()
            if row is None or row['host']!=host or row['expires']<time.time() or not hmac.compare_digest(row['binding'],digest(binding)):
                raise ValueError('etat_invalide')
            db.execute('DELETE FROM oidc_transactions WHERE state=?',(digest(state),))
        token=self.client(host).fetch_token(self.backend+'/protocol/openid-connect/token',code=code,
            code_verifier=row['verifier'],timeout=5)
        response=requests.get(self.backend+'/protocol/openid-connect/certs',timeout=5)
        response.raise_for_status()
        claims=JsonWebToken(['RS256']).decode(token['id_token'],response.json(),claims_cls=CodeIDToken,
            claims_options={'iss':{'essential':True,'value':self.issuer},
                            'aud':{'essential':True,'value':self.client_id},
                            'sub':{'essential':True},'exp':{'essential':True},
                            'iat':{'essential':True},'auth_time':{'essential':True}},
            claims_params={'nonce':row['nonce'],'client_id':self.client_id,'access_token':token['access_token']})
        claims.validate(leeway=30)
        if not isinstance(claims['sub'],str) or len(claims['sub'])>255: raise ValueError('sujet_invalide')
        # Ne jamais rattacher un ancien compte par email ou preferred_username.
        compte=self.identites.appeler('identifier',self.issuer,claims['sub'])
        if row['invitation']:
            compte=self.identites.appeler('activer',self.issuer,claims['sub'],row['invitation'],row['notice'],claims.get('preferred_username'))
        if compte.get('erreur') or not compte.get('actif'): raise ValueError('invitation_requise')
        maintenant=int(time.time());secret,csrf=secrets.token_urlsafe(32),secrets.token_urlsafe(32)
        amr=claims.get('amr',[])
        if not isinstance(amr,list) or not all(isinstance(a,str) for a in amr): amr=[]
        with closing(self.connect()) as db,db:
            db.execute('INSERT INTO oidc_principals VALUES(?,?,?) ON CONFLICT(username) DO UPDATE SET issuer=excluded.issuer,subject=excluded.subject',
              (compte['utilisateur'],self.issuer,claims['sub']))
            db.execute('DELETE FROM sessions WHERE username=? AND digest NOT IN (SELECT digest FROM sessions WHERE username=? ORDER BY last_seen DESC LIMIT 19)',(compte['utilisateur'],compte['utilisateur']))
            db.execute('DELETE FROM sessions WHERE expires<? OR last_seen<?',(maintenant,maintenant-IDLE))
            db.execute('INSERT INTO sessions(digest,username,csrf,expires,last_seen,fingerprint,host,issuer,subject,auth_time,amr,sid) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
              (digest(secret),compte['utilisateur'],csrf,maintenant+LIFETIME,maintenant,self.fingerprint(),host,self.issuer,claims['sub'],str(claims['auth_time']),json.dumps(amr),claims.get('sid','')))
        # Les jetons du fournisseur ne sont pas conservés dans le navigateur,
        # les URL de retour ou la base de sessions.
        return secret,row['retour']

    def token(self,header): return cookie_token(header,COOKIE)

    def verifier_token_mcp(self,authorization):
        if authorization.startswith('Basic '):
            try:
                texte=base64.b64decode(authorization[6:],validate=True).decode('utf-8')
            except (ValueError,UnicodeError,binascii.Error):return None
            m=re.fullmatch(r'([A-Za-z0-9_.-]{1,64}):([A-Za-z0-9_-]{43})',texte)
            if not m:return None
            u=super().verifier_token_mcp('Bearer '+m[2])
            return u if u==m[1] else None
        return super().verifier_token_mcp(authorization)

    def session(self,header,host):
        secret=self.token(header)
        if not secret:return None
        now=int(time.time())
        with closing(self.connect()) as db,db:
            row=db.execute('SELECT * FROM sessions WHERE digest=? AND host=? AND expires>? AND last_seen>?',
              (digest(secret),host,now,now-IDLE)).fetchone()
            if row is None or not hmac.compare_digest(row['fingerprint'],self.fingerprint()):return None
            compte=self.identites.appeler('identifier',row['issuer'],row['subject'])
            if compte.get('erreur')=='invitation_requise':
                self.nettoyer_principal(db,row['username']);return None
            if compte.get('erreur') or not compte.get('actif') or compte.get('utilisateur')!=row['username']:return None
            db.execute('UPDATE sessions SET last_seen=? WHERE digest=?',(now,row['digest']))
        result=dict(row);result['compte']=compte
        result['mfa']=int(row['auth_time'])<=now+30 and now-int(row['auth_time'])<=300 and {'pwd','otp'}<=set(json.loads(row['amr']))
        return result

    def nettoyer_principal(self,db,u):
        for table,colonne in [('sessions','username'),('access_tokens','username'),('mcp_tokens','username'),
          ('oidc_principals','username'),('oauth_demandes','utilisateur'),('oauth_codes','utilisateur'),('oauth_jetons','utilisateur')]:
            db.execute('DELETE FROM '+table+' WHERE '+colonne+'=?',(u,))

    def nettoyer_effacements(self):
        with closing(self.connect()) as db:
            lignes=db.execute('SELECT * FROM oidc_principals').fetchall()
        for ligne in lignes:
            compte=self.identites.appeler('identifier',ligne['issuer'],ligne['subject'])
            if compte.get('erreur')=='invitation_requise':
                with closing(self.connect()) as db,db:self.nettoyer_principal(db,ligne['username'])
        now=int(time.time())
        with closing(self.connect()) as db,db:
            db.execute('DELETE FROM sessions WHERE expires<? OR last_seen<?',(now,now-IDLE))
            db.execute('DELETE FROM oidc_transactions WHERE expires<?',(now,))
            db.execute('DELETE FROM oidc_logout_replays WHERE expires<?',(now,))
            db.execute('DELETE FROM access_tokens WHERE expires<? OR revoked<?',(now-180*86400,now-180*86400))
            db.execute('DELETE FROM oauth_demandes WHERE expiration<?',(now,))
            db.execute('DELETE FROM oauth_codes WHERE expiration<?',(now,))
            db.execute('DELETE FROM oauth_jetons WHERE expiration<? OR revoque<?',(now,now-180*86400))

    def creer_token_acces(self,username,name):
        nom=name.strip()
        if not 1<=len(nom)<=80 or any(ord(c)<32 for c in nom):raise ValueError('invalid_token_name')
        now=int(time.time());secret=secrets.token_urlsafe(32)
        with closing(self.connect()) as db,db:
            db.execute('BEGIN IMMEDIATE')
            # Historique borné à 200 lignes et 20 secrets actifs par compte.
            db.execute('DELETE FROM access_tokens WHERE username=? AND (expires<? OR revoked IS NOT NULL) AND id NOT IN (SELECT id FROM access_tokens WHERE username=? ORDER BY created DESC,id DESC LIMIT 180)',(username,now,username))
            if db.execute('SELECT count(*) FROM access_tokens WHERE username=? AND revoked IS NULL AND expires>?',(username,now)).fetchone()[0]>=20:raise ValueError('token_limit')
            expires=now+365*86400
            cur=db.execute('INSERT INTO access_tokens(username,name,digest,created,expires,revoked,fingerprint) VALUES(?,?,?,?,?,NULL,?)',(username,nom,digest(secret),now,expires,self.fingerprint()))
        return {'token':secret,'id':cur.lastrowid,'name':nom,'createdAt':now,'expiresAt':expires,'active':True}

    def cookie(self,token='',clear=False):
        return f'{COOKIE}={token}; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age={0 if clear else LIFETIME}'

    def deconnexion_commune(self,token):
        response=requests.get(self.backend+'/protocol/openid-connect/certs',timeout=5);response.raise_for_status()
        c=JsonWebToken(['RS256']).decode(token,response.json(),claims_options={
          'iss':{'essential':True,'value':self.issuer},'aud':{'essential':True,'value':self.client_id},
          'iat':{'essential':True},'jti':{'essential':True}})
        c.validate(leeway=30)
        now=int(time.time())
        if abs(now-c['iat'])>120 or 'nonce' in c or not isinstance(c.get('events'),dict) or \
           'http://schemas.openid.net/event/backchannel-logout' not in c['events'] or not (c.get('sub') or c.get('sid')):
            raise ValueError('deconnexion_invalide')
        with closing(self.connect()) as db,db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM oidc_logout_replays WHERE expires<?',(now,))
            db.execute('INSERT INTO oidc_logout_replays VALUES(?,?)',(digest(c['jti']),now+300))
            utilisateurs=[r['username'] for r in db.execute('SELECT username FROM sessions WHERE issuer=? AND ((?<>? AND subject=?) OR (?<>? AND sid=?))',
              (self.issuer,c.get('sub',''),'',c.get('sub',''),c.get('sid',''),'',c.get('sid','')))]
            if c.get('sub'):
                utilisateurs += [r['username'] for r in db.execute('SELECT username FROM oidc_principals WHERE issuer=? AND subject=?',(self.issuer,c['sub']))]
            for u in set(utilisateurs):
                db.execute('DELETE FROM sessions WHERE username=?',(u,))
                db.execute('UPDATE access_tokens SET revoked=? WHERE username=?',(now,u))
                db.execute('UPDATE oauth_jetons SET revoque=? WHERE utilisateur=?',(now,u))
                db.execute('DELETE FROM mcp_tokens WHERE username=?',(u,))

class ParHote:
    def __init__(self,app,host):self.app,self.host=app,host
    def __getattr__(self,name):return getattr(self.app,name)
    def session(self,cookie):return self.app.session(cookie,self.host)

class HandlerOIDC(Handler):
    def dispatch(self):
        app=self.server.sessions;host=self.headers.get('X-Forwarded-Host','')
        if self.path=='/auth/deconnexion-commune' and self.client_address[0]=='127.0.0.1' and not host:
            host='vision.mrj.am';self.headers['X-Forwarded-Proto']='https'
        if host not in app.hosts or self.headers.get('X-Forwarded-Proto')!='https':return self.reply(403,{'error':'invalid_origin'})
        if self.path=='/auth/configuration' and self.command=='GET':
            return self.reply(200,{'mode':'oidc','connexion':'/auth/connexion','compte':app.issuer+'/account/',
                                  'notice':app.identites.appeler('notice')})
        if self.path=='/auth/deconnexion-commune' and self.command=='POST':
            if self.headers.get('Content-Type','').split(';')[0]!='application/x-www-form-urlencoded' or self.headers.get('Transfer-Encoding'):raise ValueError('parametres_invalides')
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=8192:raise ValueError('parametres_invalides')
            p=parse_qs(self.rfile.read(length).decode(),strict_parsing=True)
            if set(p)!={'logout_token'} or len(p['logout_token'])!=1:raise ValueError('parametres_invalides')
            app.deconnexion_commune(p['logout_token'][0]);return self.reply(200,{})
        if self.path.startswith('/auth/connexion') and self.command=='GET':
            q=parse_qs(urlsplit(self.path).query,strict_parsing=False)
            if set(q)-{'retour','verification'} or any(len(v)!=1 for v in q.values()): raise ValueError('parametres_invalides')
            url,binding=app.demarrer(host,q.get('retour',['/'])[0],q.get('verification',[''])[0]=='renforcee')
            return self.reply(302,headers={'Location':url,'Set-Cookie':f'{STATE_COOKIE}={binding}; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=600'})
        if self.path.startswith('/auth/retour?') and self.command=='GET':
            q=parse_qs(urlsplit(self.path).query,strict_parsing=True)
            if not {'state','code'}<=set(q) or any(len(v)!=1 for v in q.values()):raise ValueError('etat_invalide')
            secret,retour=app.terminer(host,q['state'][0],q['code'][0],self.headers.get('Cookie',''))
            return self.reply(302,headers={'Location':retour,'Set-Cookie':app.cookie(secret),'Referrer-Policy':'no-referrer'})
        if self.path=='/auth/inscription' and self.command=='POST':
            body=self.corps(host)
            if set(body)!={'invitation','notice'} or not re.fullmatch(r'[A-Za-z0-9_-]{43}',body['invitation']) or not isinstance(body['notice'],str):raise ValueError('parametres_invalides')
            url,binding=app.demarrer(host,invitation=digest(body['invitation']),notice=body['notice'])
            return self.reply(200,{'redirection':url},{'Set-Cookie':f'{STATE_COOKIE}={binding}; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=600'})
        # Le serveur OAuth MCP conserve ses clients, scopes, PKCE et audiences.
        if self.path=='/auth/invitation' and self.command=='POST':
            body=self.corps(host)
            if set(body)!={'invitation'} or not isinstance(body['invitation'],str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}',body['invitation']):raise ValueError('parametres_invalides')
            return self.reply(200,app.identites.appeler('apercu_invitation',digest(body['invitation'])))
        # Sa page de connexion utilise désormais le fournisseur commun.
        if oauth.traiter(self,ParHote(app,host),host):return
        if self.path=='/verify-mcp' and self.command=='GET':
            headers=self.headers.get_all('Authorization',[])
            u=app.verifier_token_mcp(headers[0]) if len(headers)==1 and host=='vision.mrj.am' else None
            # Une suspension ou un effacement invalide aussi les accès MCP.
            if u:
                with closing(app.connect()) as db:
                    row=db.execute('SELECT issuer,subject FROM oidc_principals WHERE username=?',(u,)).fetchone()
                c=app.identites.appeler('identifier',row['issuer'],row['subject']) if row else {}
                if not c.get('actif') or c.get('utilisateur')!=u:u=None
            return self.reply(204 if u else 401,headers={'X-Mrj-User':u} if u else {})
        session=app.session(self.headers.get('Cookie',''),host)
        if self.path in ('/verify','/verify-gestion') and self.command=='GET':
            if not session:return self.reply(401,{'error':'authentication_required'})
            if self.headers.get('X-Original-Method') not in ('GET','HEAD'):
                self.csrf(host,session)
            if self.path=='/verify-gestion' and (not session['compte']['administrateur'] or not session['mfa']):
                return self.reply(403,{'error':'verification_renforcee_requise'})
            return self.reply(204,headers={'X-Mrj-User':session['username']})
        if self.path=='/auth/session' and self.command=='GET':
            if not session:return self.reply(401,{'error':'authentication_required'})
            return self.reply(200,{'username':session['username'],'csrf':session['csrf'],'expiresAt':session['expires'],
                                  'administrateur':session['compte']['administrateur'],'verificationRenforcee':session['mfa']})
        if self.path=='/auth/logout' and self.command=='POST':
            if not session:return self.reply(401,{'error':'authentication_required'})
            self.corps(host);self.csrf(host,session);app.logout(self.headers.get('Cookie',''))
            return self.reply(200,{'signedOut':True},{'Set-Cookie':app.cookie(clear=True)})
        # Les pages et tokens nommés continuent à utiliser l'implémentation
        # existante, à travers l'adaptateur de session lié à l'hôte.
        if self.path in ('/auth/mcp','/auth/mcp.js','/auth/style.css','/auth/mcp-token','/auth/access-tokens'):
            proxy=ParHote(app,host)
            original=self.server
            class Serveur: pass
            temporaire=Serveur();temporaire.sessions=proxy
            self.server=temporaire
            try:return super().dispatch()
            finally:self.server=original
        return self.reply(404,{'error':'not_found'})

    def csrf(self,host,session):
        if self.headers.get('Origin')!='https://'+host or not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),session['csrf']):
            raise ValueError('csrf_required')

    def corps(self,host):
        if self.headers.get('Origin')!='https://'+host or self.headers.get('Content-Type','').split(';')[0]!='application/json' or self.headers.get('Transfer-Encoding'):
            raise ValueError('invalid_origin')
        length=int(self.headers.get('Content-Length','0'))
        if not 0<length<=8192:raise ValueError('invalid_input')
        value=json.loads(self.rfile.read(length))
        if not isinstance(value,dict):raise ValueError('invalid_input')
        return value

    def handle_method(self):
        try:self.dispatch()
        except (ValueError,TypeError,KeyError,UnicodeError) as error:
            self.reply(403 if str(error)=='csrf_required' else 400,{'error':'csrf_required' if str(error)=='csrf_required' else 'invalid_input'})
        except Exception:
            # Aucun jeton, contenu ou détail de base dans la réponse ou les logs.
            self.reply(503,{'error':'unavailable'})
    do_GET=handle_method
    do_POST=handle_method

def creer_sessions():
    env=os.environ
    return SessionsOIDC(env['MRJ_AUTH_DATABASE'],env['MRJ_AUTH_CREDENTIALS'],env['MRJ_AUTH_DOMAIN'],
      env['MRJ_AUTH_HOSTS'].split(','),env['MRJ_OIDC_ISSUER'],env['MRJ_OIDC_BACKEND'],env['MRJ_OIDC_CLIENT'],
      env['MRJ_OIDC_SECRET_FILE'],Identites(env['MRJ_IDENTITES_DSN']))
