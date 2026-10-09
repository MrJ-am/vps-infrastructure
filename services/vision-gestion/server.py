"""API administrative : métadonnées uniquement, rôle SQL sans accès métier."""
import hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
import re
import secrets
import datetime
import uuid

import psycopg

CHAMPS={
 'lister_comptes':{'debut'}, 'lister_invitations':{'debut'},
 'modifier_compte':{'utilisateur','version','administrateur','actif','quota_octets','limites'},
 'demander_suppression':{'utilisateur','version'}, 'annuler_suppression':{'utilisateur','version'},
 'creer_invitation':{'intitule','maximum','quota_octets','limites','expire_a'},
 'modifier_invitation':{'id','version','intitule','maximum','quota_octets','limites','expire_a','retroactif','revoquer'},
}
REQUIS={'modifier_compte':{'utilisateur','version'},'creer_invitation':{'intitule','maximum','expire_a'},
        'demander_suppression':{'utilisateur','version'},'annuler_suppression':{'utilisateur','version'},
        'modifier_invitation':{'id','version'}}

def verifier(operation,p):
    if operation not in CHAMPS or not isinstance(p,dict) or set(p)-CHAMPS[operation] or not REQUIS.get(operation,set())<=set(p):
        raise ValueError('parametres_invalides')
    for champ,valeur in p.items():
        if champ in ('administrateur','actif','retroactif','revoquer'):
            valide=type(valeur) is bool
        elif champ in ('debut','version','maximum','quota_octets'):
            borne={'debut':(0,100000),'version':(1,2**53-1),'maximum':(1,100000),'quota_octets':(1,1000000000)}[champ]
            valide=type(valeur) is int and borne[0]<=valeur<=borne[1]
        elif champ=='utilisateur':
            valide=isinstance(valeur,str) and bool(re.fullmatch(r'[A-Za-z0-9_.-]{1,64}',valeur))
        elif champ=='intitule':
            valide=isinstance(valeur,str) and 1<=len(valeur.strip())<=100 and not any(ord(c)<32 for c in valeur)
        elif champ=='id':
            try:valide=isinstance(valeur,str) and str(uuid.UUID(valeur))==valeur
            except (ValueError,TypeError,AttributeError):valide=False
        elif champ=='expire_a':
            try:valide=isinstance(valeur,str) and len(valeur)<=40 and datetime.datetime.fromisoformat(valeur.replace('Z','+00:00')).tzinfo is not None
            except (ValueError,TypeError,AttributeError):valide=False
        elif champ=='limites':
            defauts={'fiches':1000,'items_par_fiche':500,'mots_item':500,'octets_item':8000,'mots_fiche':2000,'octets_fiche':32000,'mots_note':200,'octets_note':2000}
            valide=isinstance(valeur,dict) and set(valeur)==set(defauts) and all(type(v) is int and 1<=v<=defauts[k]*10 for k,v in valeur.items())
        else:valide=False
        if not valide:raise ValueError('parametres_invalides')

def administrer(dsn,acteur,operation,parametres):
    verifier(operation,parametres)
    p=dict(parametres);secret=None
    if operation=='creer_invitation':
        secret=secrets.token_urlsafe(32)
        p['condensat']=hashlib.sha256(secret.encode()).hexdigest()
    # Les contrôles de date de l'interface affichent explicitement UTC.
    with psycopg.connect(dsn,options='-c timezone=UTC') as db:
        resultat=db.execute('SELECT vision_gestion.administrer(%s,%s,%s)',(acteur,operation,json.dumps(p))).fetchone()[0]
    if secret:resultat['lien']='https://vision.mrj.am/invitation#'+secret
    return resultat

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def setup(self):super().setup();self.connection.settimeout(10)
    def reply(self,status,payload):
        data=json.dumps(payload,ensure_ascii=False).encode()
        self.send_response(status)
        for k,v in {'Content-Type':'application/json; charset=utf-8','Content-Length':str(len(data)),
                    'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer'}.items():self.send_header(k,v)
        self.end_headers();self.wfile.write(data)
    def do_POST(self):
        acteur=self.headers.get('X-Mrj-User','')
        if self.headers.get_all('X-Vision-Administration')!=['1'] or not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}',acteur):
            return self.reply(401,{'erreur':'identite_requise'})
        if self.headers.get('Content-Type','').split(';')[0]!='application/json' or self.headers.get('Transfer-Encoding'):
            return self.reply(415,{'erreur':'json_requis'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=8192:raise ValueError('parametres_invalides')
            p=json.loads(self.rfile.read(length));op=self.path.removeprefix('/api/gestion/')
            if not self.path.startswith('/api/gestion/'):raise ValueError('operation_inconnue')
            return self.reply(200,administrer(os.environ['VISION_GESTION_DSN'],acteur,op,p))
        except (ValueError,UnicodeError):return self.reply(400,{'erreur':'parametres_invalides'})
        except psycopg.errors.RaiseException as error:
            code=error.diag.message_primary
            permis={'administration_interdite','conflit','dernier_administrateur','budget_insuffisant',
                    'compte_introuvable','invitation_introuvable','maximum_inferieur_aux_inscriptions','maximum_inferieur_aux_reservations',
                    'limites_invalides','expiration_invalide','preavis_deja_engage','preavis_introuvable',
                    'export_a_preserver','compte_suspendu','effacement_engage'}
            return self.reply(403 if code=='administration_interdite' else 409 if code=='conflit' else 400,
                              {'erreur':code if code in permis else 'parametres_invalides'})
        except psycopg.IntegrityError:return self.reply(400,{'erreur':'parametres_invalides'})
        except psycopg.Error:return self.reply(503,{'erreur':'base_indisponible'})

if __name__=='__main__':
    os.umask(0o077)
    ThreadingHTTPServer(('127.0.0.1',3024),Handler).serve_forever()
