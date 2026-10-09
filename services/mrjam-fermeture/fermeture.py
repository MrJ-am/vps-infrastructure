"""Fermeture commune sur intention personnelle attestée par Keycloak.

Le service écoute uniquement sur loopback, sans route Nginx. Les contenus des
outils ne sont jamais lus. Le registre minimal est chiffré avant tout envoi.
"""
from contextlib import closing
import fcntl
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import threading
import time

import psycopg
import requests
from courriel import FileCourriel, adresse, lire_prive, verifier_smtp

ISSUER = 'https://log.mrj.am/realms/mrjam'
BACKEND = 'http://127.0.0.1:8085/realms/mrjam'
ADMIN = 'http://127.0.0.1:8085/admin/realms/mrjam'

def secret_prive(chemin):
    fd=os.open(chemin,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd) as f:
        s=os.fstat(f.fileno())
        if not stat.S_ISREG(s.st_mode) or s.st_mode&0o077 or s.st_uid not in (0,os.geteuid()):raise ValueError('secret_non_prive')
        valeur=f.read(128).strip()
    if not re.fullmatch(r'[A-Za-z0-9_-]{43}',valeur):raise ValueError('secret_invalide')
    return valeur


def verifier_registre(p):
    if not isinstance(p, dict) or set(p) != {'version', 'type', 'emetteur', 'sujet', 'confirmee_a', 'outils'}:
        raise ValueError('registre_invalide')
    if p['version'] != 2 or p['type'] != 'fermeture_commune' or p['emetteur'] != ISSUER:
        raise ValueError('registre_invalide')
    if not isinstance(p['sujet'], str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}', p['sujet']):
        raise ValueError('registre_invalide')
    if type(p['confirmee_a']) is not int or p['confirmee_a'] <= 0 or not isinstance(p['outils'], dict) or set(p['outils']) != {'vision'}:
        raise ValueError('registre_invalide')
    users = p['outils']['vision']
    if not isinstance(users, list) or len(users) > 10 or not all(isinstance(u, str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,64}', u) for u in users):
        raise ValueError('registre_invalide')
    return p


class Fermeture:
    def __init__(self, dsn, root, smtp, config, secret_client, secret_hook, age='age'):
        self.dsn, self.root = dsn, Path(root)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.root.is_symlink() or self.root.stat().st_mode & 0o077:
            raise ValueError('repertoire_non_prive')
        self.smtp = verifier_smtp(smtp); self.config = config
        adresse(config['adresse_exploitant'])
        if not re.fullmatch(r'age1[0-9a-z]{58}', config['recipient_age']):
            raise ValueError('cle_chiffrement_invalide')
        self.secret_client, self.secret_hook, self.age = secret_client, secret_hook, age
        self.verrou = threading.RLock()
        self.file = FileCourriel(self.root/'courriels.sqlite', smtp['from_address'])
        with self.file.ouvrir() as db:
            db.execute('CREATE TABLE IF NOT EXISTS fermetures (sujet TEXT PRIMARY KEY, outils_effaces INTEGER, terminee INTEGER)')

    def sql(self, op, sujet):
        sql = {'comptes': "SELECT vision_gestion.engager_fermeture_identite(%s,%s,'FERMER MON COMPTE')",
               'effacer': "SELECT vision_gestion.effacer_identite_cycle(%s,%s,'FERMER MON COMPTE')"}[op]
        with psycopg.connect(self.dsn) as db:
            return db.execute(sql, (ISSUER, sujet)).fetchone()[0]

    def registre(self, sujet):
        chemin = self.root/'effacements.jsonl'
        fd = os.open(chemin, os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            with os.fdopen(fd, 'r+', encoding='utf-8') as f:
                fd = None
                for ligne in f:
                    p = verifier_registre(json.loads(ligne))
                    if p['sujet'] == sujet:
                        return p
                p = verifier_registre({'version': 2, 'type': 'fermeture_commune', 'emetteur': ISSUER,
                    'sujet': sujet, 'confirmee_a': int(time.time()), 'outils': {'vision': self.sql('comptes', sujet)}})
                f.write(json.dumps(p, separators=(',', ':'))+'\n'); f.flush(); os.fsync(f.fileno())
                self.file.synchroniser_repertoire()
                return p
        finally:
            if fd is not None: os.close(fd)

    def preparer(self, sujet, confirmation):
        if confirmation != 'FERMER MON COMPTE' or not isinstance(sujet, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}', sujet):
            raise ValueError('confirmation_requise')
        with self.verrou:
            p = self.registre(sujet)
            cle = 'fermeture:'+hashlib.sha256((sujet+':'+str(p['confirmee_a'])).encode()).hexdigest()
            if not self.file.etat(cle):
                chiffre = subprocess.run([self.age, '-r', self.config['recipient_age']],
                    input=json.dumps(p, separators=(',', ':')).encode(), stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL, check=True, timeout=10).stdout
                self.file.ajouter(cle, self.config['adresse_exploitant'], 'MrJ.am — registre chiffré d’effacement',
                    'Une intention de fermeture commune est jointe, chiffrée pour la clé de restauration.\n'
                    'Conserver cette pièce pour appliquer les effacements avant toute réouverture après restauration.', chiffre)
            self.file.traiter(self.smtp, cle=cle)
            if self.file.etat(cle)['etat'] != 'accepte_relais':
                return False
            with self.file.ouvrir() as db:
                fait = db.execute('SELECT outils_effaces FROM fermetures WHERE sujet=?', (sujet,)).fetchone()
            if not fait or not fait[0]:
                self.sql('effacer', sujet)
                r = requests.post('http://127.0.0.1:3027/interne/effacer',
                    headers={'Authorization': 'Bearer '+self.secret_hook}, json={'sujet': sujet}, timeout=10)
                r.raise_for_status()
                with self.file.ouvrir() as db:
                    db.execute('INSERT INTO fermetures(sujet,outils_effaces) VALUES(?,?) ON CONFLICT(sujet) DO UPDATE SET outils_effaces=excluded.outils_effaces',
                               (sujet, int(time.time())))
            return True

    def retirer_identite(self, sujet):
        with self.file.ouvrir() as db:
            fait = db.execute('SELECT terminee FROM fermetures WHERE sujet=?', (sujet,)).fetchone()
        if fait and fait[0]: return
        r = requests.post(BACKEND+'/protocol/openid-connect/token', data={'client_id': 'mrjam-fermeture',
            'client_secret': self.secret_client, 'grant_type': 'client_credentials'}, timeout=10)
        r.raise_for_status(); entetes = {'Authorization': 'Bearer '+r.json()['access_token']}
        r = requests.delete(ADMIN+'/users/'+sujet, headers=entetes, timeout=10)
        if r.status_code != 404: r.raise_for_status()
        with self.file.ouvrir() as db:
            db.execute('UPDATE fermetures SET terminee=? WHERE sujet=?', (int(time.time()), sujet))

    def traiter(self):
        with self.verrou:
            chemin = self.root/'effacements.jsonl'
            if chemin.exists():
                for ligne in chemin.read_text().splitlines():
                    p = verifier_registre(json.loads(ligne))
                    # Laisser l'action native terminer sa transaction ; une panne
                    # ne transforme pas l'intention confirmée en compte conservé.
                    if p['confirmee_a']+120 > time.time(): continue
                    try:
                        if self.preparer(p['sujet'], 'FERMER MON COMPTE'):
                            self.retirer_identite(p['sujet'])
                    except (OSError, requests.RequestException, psycopg.Error, ValueError, subprocess.SubprocessError):
                        continue
            self.file.purger()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def setup(self): super().setup(); self.connection.settimeout(10)
    def reply(self, code):
        data = b'{"demande_enregistree":true}' if code in (200, 202) else b'{"erreur":"fermeture_indisponible"}'
        self.send_response(code)
        self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store'); self.end_headers(); self.wfile.write(data)
    def do_POST(self):
        entete = self.headers.get_all('Authorization')
        if self.path != '/fermer' or not entete or len(entete) != 1 or not hmac.compare_digest(entete[0], 'Bearer '+self.server.app.secret_hook):
            return self.reply(403)
        if self.headers.get('Content-Type') != 'application/json' or self.headers.get('Transfer-Encoding'):
            return self.reply(400)
        try:
            n = int(self.headers.get('Content-Length', '0'))
            if not 0 < n <= 1024: raise ValueError()
            p = json.loads(self.rfile.read(n))
            if not isinstance(p, dict) or set(p) != {'emetteur', 'sujet', 'confirmation'} or p['emetteur'] != ISSUER: raise ValueError()
            self.reply(200 if self.server.app.preparer(p['sujet'], p['confirmation']) else 202)
        except (ValueError, UnicodeError): self.reply(400)
        except Exception: self.reply(503)


if __name__ == '__main__':
    os.umask(0o077)
    # Ces secrets textuels sont des credentials systemd privés, pas des arguments.
    app = Fermeture(os.environ['MRJ_FERMETURE_DSN'], '/var/lib/mrjam-fermeture',
        lire_prive(os.environ['MRJ_SMTP_SECRET']), lire_prive(os.environ['MRJ_FERMETURE_CONFIG']),
        secret_prive(os.environ['MRJ_FERMETURE_CLIENT']), secret_prive(os.environ['MRJ_FERMETURE_HOOK']),
        os.environ.get('AGE', 'age'))
    def entretien():
        while True:
            try: app.traiter()
            except Exception: pass
            time.sleep(60)
    threading.Thread(target=entretien, daemon=True).start()
    serveur = ThreadingHTTPServer(('127.0.0.1', 3028), Handler); serveur.app = app; serveur.serve_forever()
