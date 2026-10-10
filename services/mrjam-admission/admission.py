"""Admission privée : invitation, courriel vérifié et contrôle proportionné.

Le navigateur ne choisit jamais un sujet OIDC ni les droits d'une identité.
L'inscription native demeure fermée. Les contrôles manuels sont effectués par
l'exploitant depuis Actions, sans rôle d'administration IdP dans Vision.
"""
import argparse
from contextlib import closing
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import time
import uuid

import psycopg
import requests

from courriel import FileCourriel, adresse, lire_prive, lire_secret_prive, verifier_smtp

ISSUER = 'https://log.mrj.am/realms/mrjam'
BACKEND = 'http://127.0.0.1:8085/realms/mrjam'
ADMIN = 'http://127.0.0.1:8085/admin/realms/mrjam'
MESSAGE = {'demande_enregistree': True,
           'information': 'Vérifiez votre boîte de courrier. Une validation complémentaire peut être nécessaire avant l’admission.'}


def secret_prive(chemin):
    return lire_secret_prive(chemin)


def condensat(valeur):
    return hashlib.sha256(valeur.encode()).hexdigest()


def verifier(p):
    if not isinstance(p, dict) or set(p) != {'invitation', 'notice', 'courriel', 'pays', 'age', 'parent', 'pseudonyme'}:
        raise ValueError('parametres_invalides')
    if not all(isinstance(v, str) for v in p.values()):
        raise ValueError('parametres_invalides')
    if not re.fullmatch(r'[A-Za-z0-9_-]{43}', p['invitation']) or not 1 <= len(p['notice']) <= 100:
        raise ValueError('parametres_invalides')
    adresse(p['courriel'])
    if not 2 <= len(p['pays'].strip()) <= 80 or any(ord(c) < 32 for c in p['pays'] + p['pseudonyme']):
        raise ValueError('parametres_invalides')
    if p['age'] not in ('moins15', '15a17', 'majeur') or len(p['pseudonyme']) > 100:
        raise ValueError('parametres_invalides')
    pays = p['pays'].strip()
    if pays.casefold() in ('france', 'fr', 'française', 'francais'):
        pays = 'France'
    # La règle française n'est jamais appliquée automatiquement à l'étranger.
    parental = pays == 'France' and p['age'] == 'moins15'
    if p['parent']:
        adresse(p['parent'])
        if p['parent'].casefold() == p['courriel'].casefold():
            raise ValueError('parent_distinct_requis')
    if parental and not p['parent']:
        raise ValueError('accord_parental_requis')
    return {**p, 'courriel': p['courriel'].casefold(), 'parent': p['parent'].casefold(),
            'pays': pays, 'parental': parental, 'manuel': p['age'] != 'majeur' or pays != 'France'}


class Admission:
    def __init__(self, dsn, repertoire, smtp, secret):
        self.dsn, self.smtp, self.secret = dsn, smtp, secret
        self.root = Path(repertoire)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.root.is_symlink() or self.root.stat().st_mode & 0o077:
            raise ValueError('repertoire_non_prive')
        self.chemin = self.root / 'admissions.sqlite'
        if self.chemin.is_symlink():
            raise ValueError('fichier_non_prive')
        self.verrou = threading.Lock()
        self.file = FileCourriel(self.root / 'courriels.sqlite', smtp['from_address'])
        with closing(self.ouvrir()) as db, db:
            db.executescript('''CREATE TABLE IF NOT EXISTS demandes (
              id TEXT PRIMARY KEY, invitation TEXT NOT NULL, notice TEXT NOT NULL,
              courriel TEXT NOT NULL, pays TEXT NOT NULL, age TEXT NOT NULL,
              parent TEXT NOT NULL, pseudonyme TEXT NOT NULL, parental INTEGER NOT NULL,
              manuel INTEGER NOT NULL, verification TEXT UNIQUE, accord TEXT UNIQUE,
              verifie_a INTEGER, accord_a INTEGER, controle_a INTEGER,
              methode TEXT, reference TEXT, source_pays TEXT,
              sujet TEXT, nouvel_utilisateur INTEGER NOT NULL DEFAULT 0,
              etat TEXT NOT NULL DEFAULT 'attente', cree INTEGER NOT NULL, expire INTEGER NOT NULL,
              terminee INTEGER);
              CREATE INDEX IF NOT EXISTS demandes_courriel ON demandes(courriel,cree);''')

    def ouvrir(self):
        db = sqlite3.connect(self.chemin, timeout=30)
        os.chmod(self.chemin, 0o600)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA synchronous=FULL')
        db.execute('PRAGMA journal_mode=DELETE')
        return db

    def sql(self, operation, *args):
        commandes = {'reserver': 'SELECT vision_gestion.reserver_admission(%s,%s,%s)',
                     'certifier': 'SELECT vision_gestion.certifier_admission(%s,%s,%s,%s)',
                     'activer': 'SELECT vision_gestion.activer(%s,%s,%s,%s,%s)',
                     'annuler': 'SELECT vision_gestion.annuler_admission(%s)',
                     'identifier': 'SELECT vision_gestion.identifier(%s,%s)'}
        with psycopg.connect(self.dsn) as db:
            return db.execute(commandes[operation], args).fetchone()[0]

    def demander(self, p):
        p = verifier(p)
        maintenant = int(time.time())
        with self.verrou, closing(self.ouvrir()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            # Aucun indicateur public d'existence d'un compte commun.
            if db.execute("SELECT 1 FROM demandes WHERE courriel=? AND expire>? AND etat='attente'",
                          (p['courriel'], maintenant)).fetchone():
                return MESSAGE
            total = db.execute('SELECT count(*) FROM demandes WHERE cree>?', (maintenant-86400,)).fetchone()[0]
            individuel = db.execute('SELECT count(*) FROM demandes WHERE courriel=? AND cree>?',
                                     (p['courriel'], maintenant-86400)).fetchone()[0]
            parents = db.execute('SELECT count(*) FROM demandes WHERE parent=? AND cree>? AND parent<>\'\'',
                                 (p['parent'], maintenant-86400)).fetchone()[0]
            if total >= 50 or individuel >= 3 or parents >= 3:
                raise ValueError('trop_de_demandes')
            identifiant = str(uuid.uuid4())
            self.sql('reserver', identifiant, condensat(p['invitation']), p['notice'])
            verification = secrets.token_urlsafe(32)
            accord = secrets.token_urlsafe(32) if p['parent'] else None
            # Les liens sont seulement dans le fragment, jamais dans les journaux HTTP.
            self.file.ajouter('admission:'+identifiant, p['courriel'], 'MrJ.am — vérifier votre adresse',
                'Une demande d’accès à Vision a été faite avec cette adresse.\n'
                'Votre compte MrJ.am sera commun aux outils qui vous auront été ouverts.\n'
                'Ouvrez ce lien puis confirmez dans la page (48 heures) :\n'
                'https://vision.mrj.am/admission#'+verification+'\n'
                'Si vous n’avez rien demandé, ignorez ce message. Aucun compte n’est créé à ce stade.')
            if accord:
                self.file.ajouter('parent:'+identifiant, p['parent'], 'MrJ.am — accord d’un représentant légal',
                    'Un jeune souhaite utiliser Vision, outil personnel de fiches et de révision.\n'
                    'Le contenu reste privé dans l’application, mais l’exploitant et l’hébergeur peuvent techniquement y accéder. '
                    'N’y inscrire aucune donnée personnelle sensible. Le jeune choisit lui-même son LLM et ses éventuels destinataires.\n'
                    'Notice : https://vision.mrj.am/privacy — contact : RGPD@MrJ.am\n'
                    'Si vous êtes son représentant légal et approuvez cet usage, ouvrez ce lien (sept jours) puis confirmez :\n'
                    'https://vision.mrj.am/admission#'+accord+'\n'
                    'La confirmation sera suivie d’une vérification manuelle proportionnée de votre qualité et des règles applicables. '
                    'Elle ne suffit pas à créer le compte. N’envoyez pas spontanément de pièce d’identité. '
                    'Après confirmation, écrivez à RGPD@MrJ.am avec la référence '+identifiant+' pour organiser cette vérification. '
                    'Vous pourrez retirer cet accord auprès du contact indiqué. Si vous n’êtes pas concerné, ignorez ce courrier.')
            db.execute('''INSERT INTO demandes(id,invitation,notice,courriel,pays,age,parent,pseudonyme,
                parental,manuel,verification,accord,cree,expire) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (identifiant, condensat(p['invitation']), p['notice'], p['courriel'], p['pays'], p['age'],
                 p['parent'], p['pseudonyme'], int(p['parental']), int(p['manuel']),
                 condensat(verification), condensat(accord) if accord else None, maintenant, maintenant+7*86400))
        return MESSAGE

    def apercu(self, token):
        if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
            raise ValueError('lien_invalide')
        with closing(self.ouvrir()) as db:
            d = db.execute('SELECT * FROM demandes WHERE verification=? OR accord=?',
                           (condensat(token), condensat(token))).fetchone()
        if not d or d['expire'] <= time.time() or d['etat'] != 'attente':
            raise ValueError('lien_invalide')
        parent = d['accord'] == condensat(token)
        if not parent and d['cree']+48*3600 <= time.time():
            raise ValueError('lien_invalide')
        return {'type': 'parent' if parent else 'adresse'}

    def confirmer(self, token, acceptation=False):
        if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
            raise ValueError('lien_invalide')
        if acceptation is not True:
            raise ValueError('confirmation_requise')
        maintenant = int(time.time())
        with self.verrou, closing(self.ouvrir()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            d = db.execute('SELECT * FROM demandes WHERE verification=? OR accord=?',
                           (condensat(token), condensat(token))).fetchone()
            if not d or d['expire'] <= maintenant or d['etat'] != 'attente':
                raise ValueError('lien_invalide')
            if d['verification'] == condensat(token):
                if d['cree']+48*3600 <= maintenant:
                    raise ValueError('lien_invalide')
                db.execute('UPDATE demandes SET verifie_a=?,verification=NULL WHERE id=?', (maintenant, d['id']))
            else:
                db.execute('UPDATE demandes SET accord_a=?,accord=NULL WHERE id=?', (maintenant, d['id']))
        return {'confirmee': True, 'information': 'Confirmation enregistrée. Vous recevrez un courrier lorsque l’accès sera ouvert. Une vérification manuelle peut encore être nécessaire.'}

    def approuver(self, identifiant, methode, reference, source_pays):
        if methode not in ('entretien', 'verification_relation', 'controle_pays'):
            raise ValueError('methode_invalide')
        if not reference or len(reference) > 160 or any(ord(c) < 32 for c in reference):
            raise ValueError('reference_minimale_requise')
        if not isinstance(source_pays, str) or not source_pays.startswith('https://') or len(source_pays) > 500:
            raise ValueError('source_officielle_requise')
        with self.verrou, closing(self.ouvrir()) as db, db:
            d = db.execute('SELECT * FROM demandes WHERE id=?', (identifiant,)).fetchone()
            if not d or d['etat'] != 'attente' or d['expire'] <= time.time() or not d['verifie_a']:
                raise ValueError('demande_non_verifiee')
            if (d['parental'] or d['parent']) and not d['accord_a']:
                raise ValueError('accord_parental_non_confirme')
            if d['parental'] and methode == 'controle_pays':
                raise ValueError('verification_representant_requise')
            db.execute('UPDATE demandes SET controle_a=?,methode=?,reference=?,source_pays=? WHERE id=?',
                       (int(time.time()), methode, reference, source_pays, identifiant))

    def effacer_sujet(self, sujet):
        if not isinstance(sujet, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}', sujet):
            raise ValueError('sujet_invalide')
        with self.verrou, closing(self.ouvrir()) as db, db:
            # Avant le retrait natif, annuler aussi une demande personnelle
            # encore sans sujet. Elle ne doit pas recréer l'identité fermée.
            # L'adresse est lue dans l'IdP privé, jamais fournie par le navigateur
            # ni conservée dans le registre extérieur des effacements.
            r=requests.get(ADMIN+'/users/'+sujet,headers=self.jeton(),timeout=10)
            courriel=''
            if r.status_code!=404:
                r.raise_for_status();profil=r.json()
                if profil.get('emailVerified') and profil.get('email'):
                    courriel=profil['email'].casefold()
            demandes = db.execute('SELECT id FROM demandes WHERE sujet=? OR (courriel<>? AND lower(courriel)=?)', (sujet,'',courriel)).fetchall()
            for d in demandes:
                self.sql('annuler',d['id'])
                with self.file.ouvrir() as file:
                    for prefixe in ('admission:', 'parent:', 'admis:'):
                        file.execute('DELETE FROM courriels WHERE cle=?', (prefixe+d['id'],))
            for d in demandes:db.execute('DELETE FROM demandes WHERE id=?',(d['id'],))

    def jeton(self):
        r = requests.post(BACKEND+'/protocol/openid-connect/token',
            data={'grant_type': 'client_credentials', 'client_id': 'mrjam-admission', 'client_secret': self.secret}, timeout=10)
        r.raise_for_status()
        return {'Authorization': 'Bearer '+r.json()['access_token']}

    def provisionner(self, d):
        deja_admise = d['sujet'] and not self.sql('identifier', ISSUER, d['sujet']).get('erreur')
        if not deja_admise:
            # Recontrôler l'invitation après les éventuels jours de vérification.
            self.sql('reserver', d['id'], d['invitation'], d['notice'])
        entetes = self.jeton()
        sujet, nouveau = d['sujet'], bool(d['nouvel_utilisateur'])
        if not sujet:
            # Un compte existant vérifié peut obtenir un droit Vision ; ni ses
            # anciens contenus ni sa session ne sont attribués par courriel.
            r = requests.get(ADMIN+'/users', headers=entetes,
                             params={'email': d['courriel'], 'exact': 'true', 'max': 2}, timeout=10)
            r.raise_for_status()
            propre = [u for u in r.json() if u.get('username') == 'admission-'+d['id'] and u.get('email', '').casefold() == d['courriel']]
            candidats = [u for u in r.json() if u.get('email', '').casefold() == d['courriel'] and u.get('emailVerified') is True]
            if len(propre) == 1:
                sujet, nouveau = propre[0]['id'], True
            elif len(candidats) == 1:
                sujet = candidats[0]['id']
                if not candidats[0].get('enabled'):
                    raise ValueError('identite_indisponible')
            elif r.json():
                # Ne jamais s'approprier/réinitialiser un compte non vérifié.
                raise ValueError('identite_indisponible')
            else:
                nom = 'admission-'+d['id']
                r = requests.get(ADMIN+'/users', headers=entetes, params={'username': nom, 'exact': 'true'}, timeout=10)
                r.raise_for_status()
                anciens = r.json()
                if not anciens:
                    r = requests.post(ADMIN+'/users', headers=entetes,
                        json={'username': nom, 'email': d['courriel'], 'emailVerified': True,
                              'enabled': False, 'requiredActions': ['UPDATE_PASSWORD']}, timeout=10)
                    if r.status_code != 201:
                        r.raise_for_status()
                        raise ValueError('creation_identite_refusee')
                    sujet = r.headers['Location'].rsplit('/', 1)[-1]
                else:
                    if len(anciens) != 1 or anciens[0].get('email', '').casefold() != d['courriel']:
                        raise ValueError('identite_incompatible')
                    sujet = anciens[0]['id']
                nouveau = True
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', sujet):
                raise ValueError('sujet_invalide')
            with closing(self.ouvrir()) as db, db:
                db.execute('UPDATE demandes SET sujet=?,nouvel_utilisateur=? WHERE id=?', (sujet, int(nouveau), d['id']))
        self.sql('certifier', d['id'], ISSUER, sujet, d['notice'])
        self.sql('activer', ISSUER, sujet, d['invitation'], d['notice'], d['pseudonyme'])
        with closing(self.ouvrir()) as db, db:
            db.execute("UPDATE demandes SET etat='provisionnee' WHERE id=?", (d['id'],))
        if nouveau:
            r = requests.put(ADMIN+'/users/'+sujet, headers=entetes, json={'enabled': True}, timeout=10)
            r.raise_for_status()
            # Le mot de passe est choisi dans Keycloak, jamais lu par ce service.
            r = requests.put(ADMIN+'/users/'+sujet+'/execute-actions-email', headers=entetes,
                             params={'lifespan': 600}, json=['UPDATE_PASSWORD'], timeout=10)
            r.raise_for_status()
        self.file.ajouter('admis:'+d['id'], d['courriel'], 'MrJ.am — votre accès à Vision',
            'Votre accès à Vision est ouvert. '+('Un courrier distinct vous permet de choisir votre mot de passe. ' if nouveau else '')+
            'Connectez-vous avec votre adresse et votre mot de passe habituel : https://vision.mrj.am/connexion\n'
            'Votre compte commun peut être utilisé dans les autres outils qui vous seront ouverts.\n'
            'Vous pouvez exporter et supprimer vos données depuis votre espace personnel. Notice : https://vision.mrj.am/privacy')
        with closing(self.ouvrir()) as db, db:
            db.execute("UPDATE demandes SET etat='admise',terminee=?,verification=NULL,accord=NULL WHERE id=?", (int(time.time()), d['id']))

    def traiter(self):
        with self.verrou:
            self.file.traiter(self.smtp)
            with closing(self.ouvrir()) as db:
                lignes = db.execute("SELECT * FROM demandes WHERE etat IN ('attente','provisionnee') ORDER BY cree LIMIT 100").fetchall()
            for d in lignes:
                deja_admise = d['etat'] == 'provisionnee'
                if d['sujet'] and not deja_admise:
                    deja_admise = not self.sql('identifier', ISSUER, d['sujet']).get('erreur')
                if d['expire'] <= time.time() and not deja_admise:
                    if d['sujet'] and d['nouvel_utilisateur']:
                        entetes = self.jeton()
                        r = requests.get(ADMIN+'/users/'+d['sujet'], headers=entetes, timeout=10)
                        if r.status_code != 404:
                            r.raise_for_status(); identite = r.json()
                            if identite.get('username') != 'admission-'+d['id'] or identite.get('enabled'):
                                continue
                            r = requests.delete(ADMIN+'/users/'+d['sujet'], headers=entetes, timeout=10)
                            r.raise_for_status()
                    self.sql('annuler', d['id'])
                    self.file.annuler('admission:'+d['id']); self.file.annuler('parent:'+d['id'])
                    with closing(self.ouvrir()) as db, db:
                        db.execute("UPDATE demandes SET etat='expiree',terminee=? WHERE id=?", (int(time.time()), d['id']))
                    continue
                if not d['verifie_a'] or ((d['parental'] or d['parent']) and not d['accord_a']) or (d['manuel'] and not d['controle_a']):
                    continue
                try:
                    self.provisionner(d)
                except (requests.RequestException, psycopg.Error, ValueError, KeyError):
                    # Réessai sans journaliser adresse, jeton, réponse IdP ou preuve.
                    continue
            self.file.purger()
            with closing(self.ouvrir()) as db, db:
                db.execute("DELETE FROM demandes WHERE etat='expiree' AND terminee<?", (int(time.time())-30*86400,))
                # Après admission, seule la preuve minimale reste nécessaire.
                db.execute("UPDATE demandes SET courriel='',parent='',pseudonyme='' WHERE etat='admise' AND terminee<?", (int(time.time())-30*86400,))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def setup(self): super().setup(); self.connection.settimeout(10)
    def reply(self, statut, p):
        data = json.dumps(p, ensure_ascii=False).encode()
        self.send_response(statut)
        for k, v in {'Content-Type': 'application/json; charset=utf-8', 'Content-Length': str(len(data)),
                     'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer', 'X-Content-Type-Options': 'nosniff'}.items():
            self.send_header(k, v)
        self.end_headers(); self.wfile.write(data)
    def do_POST(self):
        if self.path == '/interne/effacer':
            attendu = getattr(self.server.app, 'fermeture_secret', None)
            entete = self.headers.get_all('Authorization')
            if not attendu or not entete or len(entete) != 1 or not hmac.compare_digest(entete[0], 'Bearer '+attendu):
                return self.reply(403, {'erreur':'operation_interdite'})
            try:
                n = int(self.headers.get('Content-Length','0'))
                if not 0 < n <= 1024 or self.headers.get('Transfer-Encoding') or self.headers.get('Content-Type') != 'application/json': raise ValueError()
                p = json.loads(self.rfile.read(n))
                if not isinstance(p, dict) or set(p) != {'sujet'}: raise ValueError()
                self.server.app.effacer_sujet(p['sujet'])
                return self.reply(200, {'efface':True})
            except Exception: return self.reply(400, {'erreur':'parametres_invalides'})
        if self.headers.get_all('Origin') != ['https://vision.mrj.am']:
            return self.reply(403, {'erreur': 'origine_refusee'})
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json' or self.headers.get('Transfer-Encoding'):
            return self.reply(415, {'erreur': 'json_requis'})
        try:
            n = int(self.headers.get('Content-Length', '0'))
            if not 0 < n <= 4096:
                raise ValueError('parametres_invalides')
            p = json.loads(self.rfile.read(n))
            if self.path == '/auth/admission':
                return self.reply(202, self.server.app.demander(p))
            if self.path == '/auth/admission/apercu' and isinstance(p, dict) and set(p) == {'token'}:
                return self.reply(200, self.server.app.apercu(p['token']))
            if self.path == '/auth/admission/confirmer' and isinstance(p, dict) and set(p) == {'token', 'acceptation'}:
                return self.reply(200, self.server.app.confirmer(p['token'], p['acceptation']))
            raise ValueError('parametres_invalides')
        except (ValueError, UnicodeError):
            return self.reply(400, {'erreur': 'demande_invalide_ou_indisponible'})
        except psycopg.Error:
            return self.reply(503, {'erreur': 'admission_indisponible'})


def charger():
    return Admission(os.environ['MRJ_ADMISSION_DSN'], os.environ.get('MRJ_ADMISSION_ETAT', '/var/lib/mrjam-admission'),
        verifier_smtp(lire_prive(os.environ['MRJ_SMTP_SECRET'])), secret_prive(os.environ['MRJ_ADMISSION_SECRET']))


if __name__ == '__main__':
    os.umask(0o077)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--approuver'); p.add_argument('--methode'); p.add_argument('--reference'); p.add_argument('--source-pays')
    p.add_argument('--lister', action='store_true')
    args = p.parse_args(); app = charger()
    if os.environ.get('MRJ_ADMISSION_FERMETURE_SECRET'): app.fermeture_secret = secret_prive(os.environ['MRJ_ADMISSION_FERMETURE_SECRET'])
    if args.approuver:
        app.approuver(args.approuver, args.methode, args.reference, args.source_pays)
        print('{"controle_enregistre":true}')
    elif args.lister:
        with closing(app.ouvrir()) as db:
            # Les journaux Actions ne reçoivent ni adresse ni justificatif.
            print(json.dumps([dict(d) for d in db.execute("SELECT id,pays,age,verifie_a,accord_a,controle_a,expire FROM demandes WHERE etat='attente' AND manuel=1 ORDER BY cree")], ensure_ascii=False))
    else:
        def entretien():
            while True:
                try: app.traiter()
                except Exception: pass
                time.sleep(60)
        threading.Thread(target=entretien, daemon=True).start()
        serveur = ThreadingHTTPServer(('127.0.0.1', 3027), Handler)
        serveur.app = app; serveur.serve_forever()
