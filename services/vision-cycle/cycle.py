"""Cycle de vie aveugle : préavis, export conservé, registre chiffré et effacement.

Ce processus privé possède une fonction SQL d'effacement mais aucun droit de
lecture pédagogique. Sa clé IdP permet de lire les métadonnées d'identité,
jamais de réinitialiser les mots de passe ou d'usurper une session.
"""
import fcntl
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import threading
import time
from urllib.parse import quote

import psycopg
import requests
import subprocess
from courriel import FileCourriel, lire_prive, lire_secret_prive, verifier_smtp, archiver_effacement, adresse


class Cycle:
    def __init__(self, dsn, repertoire, smtp, config, client_secret, age='age'):
        self.dsn, self.smtp, self.config = dsn, verifier_smtp(smtp), config
        self.repertoire = Path(repertoire)
        self.repertoire.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.repertoire.is_symlink() or self.repertoire.stat().st_mode & 0o077:
            raise ValueError('Registre non privé')
        adresse(config['adresse_exploitant'])
        self.client_secret, self.age = client_secret, age
        self.file = FileCourriel(self.repertoire / 'courriels.sqlite', smtp['from_address'])
        with self.file.ouvrir() as db:
            db.execute('CREATE TABLE IF NOT EXISTS effacements_termines(utilisateur TEXT PRIMARY KEY)')
        self.verrou = threading.RLock()

    def sql(self, operation, *args):
        requete = {'preavis':'SELECT vision_gestion.preavis_a_traiter()',
                   'constater':'SELECT vision_gestion.constater_preavis(%s,%s)',
                   'engager':'SELECT vision_gestion.engager_effacement(%s,%s)',
                   'effacer':'SELECT vision_gestion.effacer_cycle(%s,%s,%s)'}[operation]
        with psycopg.connect(self.dsn) as db:
            return db.execute(requete, args).fetchone()[0]

    def email(self, demande):
        if demande['emetteur'] != 'https://log.mrj.am/realms/mrjam':
            raise ValueError('Émetteur non prévu')
        sujet = demande['sujet']
        if not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}', sujet):
            raise ValueError('Sujet invalide')
        jeton = requests.post('http://127.0.0.1:8085/realms/mrjam/protocol/openid-connect/token',
                              data={'grant_type':'client_credentials','client_id':'mrjam-cycle',
                                    'client_secret':self.client_secret}, timeout=5)
        jeton.raise_for_status()
        reponse = requests.get('http://127.0.0.1:8085/admin/realms/mrjam/users/' + quote(sujet, safe=''),
                                headers={'Authorization':'Bearer ' + jeton.json()['access_token']}, timeout=5)
        reponse.raise_for_status()
        profil = reponse.json()
        if profil.get('id') != sujet or profil.get('emailVerified') is not True:
            raise ValueError('Adresse d’identité non vérifiée')
        return adresse(profil['email'])

    def consigner(self, utilisateur):
        if not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}', utilisateur):
            raise ValueError('Identifiant invalide')
        fd = os.open(self.repertoire / 'effacements.jsonl', os.O_CREAT | os.O_RDWR | os.O_APPEND | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            with os.fdopen(fd, 'r+', encoding='utf-8') as fichier:
                fd = None
                for ligne in fichier:
                    record = json.loads(ligne)
                    if record['utilisateur'] == utilisateur:
                        return record['confirmee_a']
                date = int(time.time())
                fichier.write(json.dumps({'utilisateur':utilisateur,'confirmee_a':date}, separators=(',', ':')) + '\n')
                fichier.flush(); os.fsync(fichier.fileno())
            self.file.synchroniser_repertoire()
            return date
        finally:
            if fd is not None: os.close(fd)

    def effacer(self, utilisateur, confirmation, demande=None):
        if confirmation != 'EFFACER VISION':
            raise ValueError('Confirmation requise')
        with self.verrou:
            with self.file.ouvrir() as db:
                if db.execute('SELECT 1 FROM effacements_termines WHERE utilisateur=?', (utilisateur,)).fetchone():
                    return {'efface':True,'identite_commune_conservee':True}
            if demande is not None and not self.sql('engager', utilisateur, demande):
                raise ValueError('Préavis annulé ou non exigible')
            date = self.consigner(utilisateur)
            statut = archiver_effacement(self.file, utilisateur, date, self.config['recipient_age'],
                                         self.config['adresse_exploitant'], self.age)
            if statut['etat'] != 'accepte_relais':
                cle = 'effacement:' + hashlib.sha256(f'{utilisateur}:{date}'.encode()).hexdigest()
                self.file.traiter(self.smtp, cle=cle)
                statut = archiver_effacement(self.file, utilisateur, date, self.config['recipient_age'],
                                             self.config['adresse_exploitant'], self.age)
            if statut['etat'] != 'accepte_relais':
                # Intention durable conservée et rejouable ; la personne est
                # informée que la confirmation externe est encore en attente.
                return {'effacement_en_attente':True,'raison':'registre_externe_en_attente'}
            try:
                resultat = self.sql('effacer', utilisateur, confirmation, demande)
            except psycopg.errors.RaiseException as erreur:
                if erreur.diag.message_primary != 'compte_introuvable': raise
                resultat = {'efface':True,'identite_commune_conservee':True}
            with self.file.ouvrir() as db:
                db.execute('INSERT OR IGNORE INTO effacements_termines VALUES(?)', (utilisateur,))
            return resultat

    def traiter(self):
        with self.verrou:
            demandes = self.sql('preavis')
            for demande in demandes:
                if demande.get('annule_a'):
                    cle = 'preavis:' + demande['id']
                    statut = self.file.etat(cle)
                    self.file.annuler(cle)
                    if statut and statut['etat'] == 'accepte_relais':
                        try:
                            self.file.ajouter('annulation:' + demande['id'], self.email(demande),
                                'Vision — annulation du préavis de suppression',
                                'Le préavis de suppression de votre compte Vision a été annulé.\n'
                                'La suppression annoncée ne sera pas exécutée. Votre compte est conservé.\n'
                                'Pour toute question : RGPD@MrJ.am.')
                        except (ValueError, requests.RequestException): pass
                    continue
                if demande['etat_courriel'] == 'accepte_relais': continue
                try:
                    self.file.ajouter('preavis:' + demande['id'], self.email(demande),
                        'Vision — préavis de suppression de vos données',
                        'L’administration a engagé une suppression de votre compte Vision.\n'
                        'Vous disposez d’au moins trente jours après l’envoi de ce message pour exporter vos données depuis « Mon compte et mes limites » : https://vision.mrj.am/#compte\n'
                        'Votre identité commune MrJ.am et les autres outils sont conservés.\n'
                        'Vous pouvez contester ou demander de l’aide à RGPD@MrJ.am.\n'
                        'L’administration peut annuler cette procédure ; elle ne peut pas consulter vos connaissances.')
                except (ValueError, requests.RequestException):
                    self.sql('constater', demande['id'], 'erreur')
            self.file.traiter(self.smtp)
            for demande in demandes:
                statut = self.file.etat('preavis:' + demande['id'])
                if statut and not demande.get('annule_a') and demande['etat_courriel'] != 'accepte_relais':
                    self.sql('constater', demande['id'], 'accepte_relais' if statut['etat'] == 'accepte_relais' else 'erreur' if statut['erreur'] else 'attente')
            # Relecture après les envois : aucune suppression à partir d'une
            # ancienne liste antérieure à une annulation ou à la fin du délai.
            for demande in self.sql('preavis'):
                if demande['exigible']:
                    try: self.effacer(demande['utilisateur'], 'EFFACER VISION', demande['id'])
                    except (ValueError, psycopg.errors.RaiseException):
                        pass  # Une annulation concurrente est toujours prioritaire.
            registre = self.repertoire / 'effacements.jsonl'
            if registre.exists():
                # Toute intention déjà engagée reste applicable après une panne,
                # même si la réponse au navigateur n'a pas été reçue.
                for ligne in registre.read_text().splitlines():
                    intention = json.loads(ligne)
                    try: self.effacer(intention['utilisateur'], 'EFFACER VISION')
                    except psycopg.errors.RaiseException as erreur:
                        if erreur.diag.message_primary != 'compte_introuvable': raise
            self.file.purger()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def setup(self): super().setup(); self.connection.settimeout(10)
    def repondre(self, status, donnees):
        corps = json.dumps(donnees).encode()
        self.send_response(status)
        for k,v in {'Content-Type':'application/json','Content-Length':str(len(corps)),
                    'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}.items(): self.send_header(k,v)
        self.end_headers(); self.wfile.write(corps)
    def do_POST(self):
        if self.path != '/api/web/effacer_compte': return self.repondre(404, {'erreur':'operation_inconnue'})
        utilisateur = self.headers.get('X-Mrj-User', '')
        if self.headers.get_all('X-Vision-Browser') != ['1'] or self.headers.get_all('X-Vision-Authenticated') != ['1'] or not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}', utilisateur):
            return self.repondre(401, {'erreur':'identite_requise'})
        try:
            if self.headers.get('Content-Type','').split(';')[0] != 'application/json' or self.headers.get('Transfer-Encoding'): raise ValueError()
            taille = int(self.headers.get('Content-Length','0'))
            if not 0 < taille <= 1024: raise ValueError()
            p = json.loads(self.rfile.read(taille))
            if p != {'confirmation':'EFFACER VISION'}: raise ValueError()
            resultat = self.server.cycle.effacer(utilisateur, p['confirmation'])
            return self.repondre(202 if resultat.get('effacement_en_attente') else 200, resultat)
        except (ValueError, UnicodeError): return self.repondre(400, {'erreur':'confirmation_requise'})
        except (psycopg.Error, OSError, requests.RequestException, subprocess.SubprocessError): return self.repondre(503, {'erreur':'effacement_indisponible'})


if __name__ == '__main__':
    os.umask(0o077)
    cycle = Cycle(os.environ['VISION_CYCLE_DSN'], '/var/lib/vision-cycle',
                  lire_prive(os.environ['MRJ_SMTP_SECRET']), lire_prive(os.environ['VISION_CYCLE_CONFIG']),
                  lire_secret_prive(os.environ['VISION_CYCLE_CLIENT_SECRET']), os.environ.get('AGE','age'))
    def reprises():
        while True:
            try: cycle.traiter()
            except Exception:
                print('Cycle de vie temporairement indisponible.', flush=True)
            time.sleep(60)
    threading.Thread(target=reprises, daemon=True).start()
    serveur = ThreadingHTTPServer(('127.0.0.1',3026), Handler); serveur.cycle = cycle; serveur.serve_forever()
