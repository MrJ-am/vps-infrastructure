"""CLI/API officiels Kanidm pour l'opérateur ; aucun serveur ou credential produit."""
import json
from pathlib import Path
import re
import subprocess

class OperationRefusee(RuntimeError):
    pass

class KanidmPrive:
    def __init__(self, paquet, config, curl, *, ca=None, port=8443, diagnostic=None):
        self.paquet=Path(paquet); self.config=Path(config); self.curl=Path(curl)
        self.ca=Path(ca) if ca else None; self.port=port
        self.diagnostic=Path(diagnostic) if diagnostic else None
        if not str(self.paquet).startswith('/nix/store/') or not 1 <= port <= 65535:
            raise OperationRefusee('Configuration privée invalide')

    def commande(self, *args):
        r=subprocess.run([str(self.paquet/'bin/kanidmd'),'-c',str(self.config),*args],
                         capture_output=True,text=True,timeout=45)
        if r.returncode:
            if self.diagnostic:
                import os
                fd=os.open(self.diagnostic,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600);os.fchmod(fd,0o600)
                with os.fdopen(fd,'w') as f:f.write(r.stdout+'\n'+r.stderr)
            raise OperationRefusee('Commande native refusée : '+args[0])
        return r.stdout

    def recuperer(self, nom):
        if nom not in ('admin','idm_admin'): raise OperationRefusee('Récupération hors périmètre')
        d=json.loads(self.commande('scripting','recover-account',nom))
        if d.get('status')!='ok' or not isinstance(d.get('output'),str):
            raise OperationRefusee('Réponse de récupération invalide')
        return d['output']

    def http(self, path, body=None, *, token=None, method=None, cookies=None, attendu=200):
        if not re.fullmatch(r'/[A-Za-z0-9_/?=&%.,:+-]{1,2048}',path):
            raise OperationRefusee('Chemin privé refusé')
        def quote(v):
            if any(ord(c)<32 or ord(c)==127 for c in v): raise OperationRefusee('Option privée refusée')
            return '"'+v.replace('\\','\\\\').replace('"','\\"')+'"'
        lines=['silent','show-error','max-time = 10','connect-timeout = 5','proxy = ""','noproxy = "*"',
               'proto = "=https"','tlsv1.2','max-filesize = 1048576',
               'url = '+quote('https://log.mrj.am'+path),
               'connect-to = '+quote(f'log.mrj.am:443:127.0.0.1:{self.port}'),
               'header = "Expect:"','write-out = "\\n%{response_code}"']
        if self.ca: lines+=['cacert = '+quote(str(self.ca))]
        if token: lines+=['header = '+quote('Authorization: Bearer '+token)]
        if cookies: lines+=['cookie = '+quote(str(cookies)),'cookie-jar = '+quote(str(cookies))]
        if method:
            if method not in ('GET','POST','PUT','DELETE','PATCH'): raise OperationRefusee('Méthode refusée')
            lines+=['request = '+quote(method)]
        if body is not None:
            lines+=['request = '+quote(method or 'POST'),'header = "Content-Type: application/json"',
                    'data = '+quote(json.dumps(body))]
        r=subprocess.run([str(self.curl),'--disable','--config','-'],input='\n'.join(lines)+'\n',
                         capture_output=True,text=True,timeout=15,umask=0o077)
        if r.returncode: raise OperationRefusee('Transport TLS privé refusé')
        text, status=r.stdout.rsplit('\n',1); status=int(status)
        if status!=attendu: raise OperationRefusee('API native refusée HTTP'+str(status))
        return json.loads(text) if text else None

    def login(self, nom, password, dossier):
        if nom not in ('admin','idm_admin'): raise OperationRefusee('Authentification opérateur hors périmètre')
        import secrets
        jar=Path(dossier)/('cookies-operateur-'+secrets.token_hex(8)); jar.touch(mode=0o600)
        try:
            for request, expected in [
                ({'step':{'init2':{'username':nom,'issue':'token','privileged':True}}},'choose'),
                ({'step':{'begin':'password'}},'continue'),
                ({'step':{'cred':{'password':password}}},'success')]:
                r=self.http('/v1/auth',request,cookies=jar)
                if expected not in r.get('state',{}): raise OperationRefusee('Authentification opérateur refusée')
            return r['state']['success']
        finally: jar.unlink(missing_ok=True)

    def configurer_proprietaire(self, plan, dossier):
        """UUID neuf explicite, enrôlement MFA avant toute authentification.

        La capacité de l'opérateur reste en mémoire et expire. Elle ne sort
        jamais de ce processus et n'est pas placée dans le monolithe.
        """
        op=self.login('idm_admin',self.recuperer('idm_admin'),dossier)
        nom=plan['name']; mail=plan['mail']
        for group in ('idm_all_accounts','idm_all_persons'):
            self.http('/v1/group/'+group+'/_attr/authsession_expiry',['7776000'],token=op,method='PUT')
        # Un seul groupe de rôle, sans droit administrateur global IdP.
        self.http('/v1/group',{'attrs':{'name':['mrjam-proprietaire-policy']}},token=op)
        for attr, vals in [('class',['account_policy']),('authsession_expiry',['604800']),
                           ('privilege_expiry',['900']),('credential_type_minimum',['mfa'])]:
            self.http('/v1/group/mrjam-proprietaire-policy/_attr/'+attr,vals,token=op,
                      method='POST' if attr=='class' else 'PUT')
        self.http('/v1/person',{'attrs':{'name':[nom],'displayname':[mail],'mail':[mail]}},token=op)
        person=self.http('/v1/person/'+nom,token=op)['attrs']
        subject=person['uuid'][0]
        self.http('/v1/group/mrjam-proprietaire-policy/_attr/member',[subject],token=op)
        self.http('/v1/oauth2/_basic',{'attrs':{'name':['mrjam-vision'],'displayname':['Vision MrJ.am'],
                    'oauth2_rs_origin_landing':['https://vision.mrj.am'],'oauth2_strict_redirect_uri':['true']}},token=op)
        self.http('/v1/oauth2/mrjam-vision/_attr/oauth2_rs_origin',['https://vision.mrj.am/auth/retour'],token=op)
        self.http('/v1/oauth2/mrjam-vision/_scopemap/idm_all_persons',['openid','profile','email'],token=op)
        secret=self.http('/v1/oauth2/mrjam-vision/_basic_secret',token=op)
        intent=self.http('/v1/person/'+subject+'/_credential/_update_intent/86400',token=op)
        if not isinstance(secret,str) or not isinstance(intent.get('token'),str):
            raise OperationRefusee('Secret client ou invitation native absent')
        # Compte technique de bootstrap, pas une méthode faible de connexion
        # permanente. La récupération future reste réservée au socket privé/root.
        self.commande('disable-account','idm_admin')
        return {'subject':subject,'client_secret':secret,'intent':intent['token']}

    def restaurer_verifier(self, backup, dossier, subject):
        """Restaurer hors ligne puis lire vraiment les entrées restaurées."""
        import tomllib
        d=Path(dossier); d.mkdir(mode=0o700)
        conf=tomllib.loads(self.config.read_text())
        cfg=d/'server.toml'
        cfg.write_text('\n'.join(['version = "2"','domain = "log.mrj.am"','origin = "https://log.mrj.am"',
            'bindaddress = "127.0.0.1:18443"','db_path = '+json.dumps(str(d/'kanidm.db')),
            'tls_chain = '+json.dumps(conf['tls_chain']), 'tls_key = '+json.dumps(conf['tls_key']),
            'adminbindpath = '+json.dumps(str(d/'admin.sock'))])+'\n')
        cfg.chmod(0o600)
        isole=KanidmPrive(self.paquet,cfg,self.curl,diagnostic=self.diagnostic)
        # Le backup en ligne1.11.2 est gzip ; le restaurateur hors ligne attend
        # du JSON décompressé. Copie privée, sans altérer l'archive chiffrée.
        import gzip
        contenu=Path(backup).read_bytes()
        if contenu.startswith(b'\x1f\x8b'): contenu=gzip.decompress(contenu)
        if len(contenu)>128*1024*1024: raise OperationRefusee('Backup décompressé hors borne')
        plain=d/'restaurer.json';plain.write_bytes(contenu);plain.chmod(0o600)
        isole.commande('database','restore',str(plain))
        plain.unlink()
        isole.commande('database','verify')
        valeurs=isole.commande('db-scan','list-id2entry')
        if subject not in valeurs or 'mrjam-vision' not in valeurs or 'mrjam-proprietaire-policy' not in valeurs:
            raise OperationRefusee('Entrées de restauration native absentes')
        return True
