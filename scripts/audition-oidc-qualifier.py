"""Parcours réel Log/Kanidm/MCP/PG, entièrement local et éphémère.

Réutilise les fixtures centrales et le chargeur ASDF. Les clés, cookies et jetons
restent dans le répertoire privé de la fixture ; aucun corps privé dans le reçu.
"""
import importlib.util
import json
import os
from pathlib import Path
import queue
import secrets
import shutil
import subprocess
import sys
import threading
import time
from urllib.parse import parse_qs, urlsplit
from assemblage import RACINE

sys.path.insert(0, str(RACINE / 'tests'))
from kanidm_reel import KanidmLocal, EchecQualification
from kanidm_politiques import creer_neuf_mfa

spec = importlib.util.spec_from_file_location('audition_pg', RACINE / 'scripts/audition-qualifier.py')
pg = importlib.util.module_from_spec(spec); spec.loader.exec_module(pg)


class LispFroid:
    def __init__(self, exe, env, root):
        self.messages = queue.Queue()
        self.log = (root / ('lisp-' + secrets.token_hex(8) + '.log')).open('w')
        os.chmod(self.log.name, 0o600)
        self.p = subprocess.Popen([exe, '--noinform', '--script', str(RACINE / 'tests/audition-oidc-froid.lisp')],
            cwd=RACINE, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, umask=0o077)
        def lire():
            for line in self.p.stdout:
                self.log.write(line); self.log.flush()
                if line.startswith('AUDITION-OIDC '): self.messages.put(line.strip())
            self.messages.put('AUDITION-OIDC ARRETE')
        self.lecteur = threading.Thread(target=lire, daemon=True); self.lecteur.start()
        self.attendre('AUDITION-OIDC PRET', 180)

    def attendre(self, attendu, timeout=90):
        try: message = self.messages.get(timeout=timeout)
        except queue.Empty: raise EchecQualification('image propre hors délai') from None
        if message != attendu:
            # Seuls type de condition et numéro public d'assertion peuvent sortir.
            raise EchecQualification(message if message.startswith('AUDITION-OIDC ECHEC ') else 'image propre arrêtée')

    def phase(self, nom):
        if nom not in ('debut', 'retour', 'preparer', 'seance', 'reprendre'):
            raise EchecQualification('phase non prévue')
        self.p.stdin.write(nom + '\n'); self.p.stdin.flush()
        self.attendre('AUDITION-OIDC OK ' + nom)

    def fermer(self):
        if self.p.poll() is None:
            self.p.stdin.close()
            try: self.p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.p.terminate(); self.p.wait(timeout=5)
        self.lecteur.join(timeout=5); self.log.close()


def qualifier():
    exe = os.environ.get('MRJAM_SBCL') or shutil.which('sbcl')
    if not exe or subprocess.check_output([exe, '--version'], text=True).strip() != 'SBCL 2.6.4':
        raise EchecQualification('SBCL verrouillé déjà installé requis')
    paquet = os.environ.get('MRJAM_KANIDM')
    curl = os.environ.get('MRJAM_CURL') or shutil.which('curl')
    if not paquet or not curl: raise EchecQualification('Kanidm1.11.2 et curl verrouillés déjà installés requis')
    debut = time.monotonic()
    with pg.postgres_isole('alice') as base, KanidmLocal(paquet, curl) as n:
        n.nom = 'fixture-audition-prof'; n.mail = 'prof@example.test'
        prof_token = creer_neuf_mfa(n); prof_uuid = n.uuid
        secret = n.creer_client_oidc()
        # Même maintenance officielle que le socle : opérateur fermé au repos,
        # récupération ponctuelle du seul compte de service, puis fermeture.
        n.commande('disable-account', 'idm_admin')
        op = n.login('idm_admin', n.recuperer('idm_admin'), privilegie=True)
        retours = ['https://vision.mrj.am/auth/retour', 'https://audition.mrj.am/auth/retour']
        status, _ = n.http('/v1/oauth2/mrjam-vision/_attr/oauth2_rs_origin', retours, token=op)
        if status != 200: raise EchecQualification('ajout de la seconde audience native refusé HTTP' + str(status))
        status, doc = n.http('/v1/oauth2/mrjam-vision', token=op)
        if status != 200 or set(doc['attrs']['oauth2_rs_origin']) != set(retours):
            raise EchecQualification('retour Vision non conservé')
        status, secret_apres = n.http('/v1/oauth2/mrjam-vision/_basic_secret', token=op)
        if status != 200 or secret_apres != secret: raise EchecQualification('secret client modifié')
        n.nom = 'fixture-audition-eleve'; n.mail = 'eleve@example.test'
        n.password = 'Synthese-' + secrets.token_urlsafe(32)
        eleve_token = creer_neuf_mfa(n); eleve_uuid = n.uuid
        n.commande('disable-account', 'idm_admin')
        fixture = n.root / 'audition-fixture.json'; fixture.touch(mode=0o600)
        resultat = n.root / 'resultat.json'; resultat.touch(mode=0o600); resultat.write_text('{}')
        http = n.root / 'http.txt'; http.touch(mode=0o600)
        d = {'secret': secret, 'curl': str(n.curl), 'ca': str(n.ca), 'port': n.port,
             'prof_uuid': prof_uuid, 'eleve_uuid': eleve_uuid, 'dsn': base.dsn,
             'base': str(n.root / 'sessions.sqlite'), 'resultat': str(resultat), 'http': str(http)}
        def ecrire(): fixture.write_text(json.dumps(d))
        ecrire()
        env = dict(os.environ, MRJAM_AUDITION_OIDC_FIXTURE=str(fixture))
        image = LispFroid(exe, env, n.root)
        try:
            def connexion(hote, retour, nom_session, acteur, token):
                d.update(hote=hote, retour=retour, nom_session=nom_session, acteur=acteur); ecrire()
                image.phase('debut')
                r = json.loads(resultat.read_text()); uri = urlsplit(r['uri'])
                query = parse_qs(uri.query, strict_parsing=True)
                if uri.netloc != 'log.mrj.am' or uri.path != '/ui/oauth2':
                    raise EchecQualification('connexion hors Log')
                state = query['state'][0]
                code = n.autoriser_code(token, 'mrjam-vision', hote, state, query['nonce'][0], query['code_challenge'][0])
                d.update(state=state, code=code); ecrire()
                image.phase('retour')
            connexion('vision.mrj.am', '/', 'vision_cookie', 'alice', prof_token)
            connexion('audition.mrj.am', '/#enseignant', 'prof_cookie', 'alice', prof_token)
            image.phase('preparer')
            connexion('audition.mrj.am', '/#seance/fixture', 'eleve_cookie', 'bob', eleve_token)
            image.phase('seance')
        finally: image.fermer()
        ancien_pid = n.processus.pid
        n.arreter(); n.demarrer()
        if ancien_pid == n.processus.pid: raise EchecQualification('redémarrage natif non effectué')
        # Nouvelle image Lisp : sessions et productions relues depuis le stockage.
        image = LispFroid(exe, env, n.root)
        try: image.phase('reprendre')
        finally: image.fermer()
        base.restaurer()
        rapport = {'format': 1, 'assertions': json.loads(resultat.read_text())['assertions'],
            'kanidm': '1.11.2', 'paquet': str(n.paquet), 'postgres': '17.11',
            'identites_mfa_reelles_isolees': 2, 'oidc_pkce_signature_tls': True,
            'retour_action_cookie_host_only': True, 'audiences_vision_audition_isolees': True,
            'csrf_refus_roles_origines': True, 'preparation_affectation_seance_aide_rapport': True,
            'rotation_rejeu_revocation_logout': True, 'restart_natif_et_image_propre': True,
            'maintenance_operateur_ferme_secret_client_preserve': True,
            'restauration': True, 'secondes': round(time.monotonic() - debut, 3),
            'production': False, 'fournisseur_llm': 'aucun essai de compte fournisseur'}
        (RACINE / 'state/audition-oidc-qualification.json').write_text(json.dumps(rapport, indent=2) + '\n')
        print(json.dumps(rapport))


if __name__ == '__main__':
    try: qualifier()
    except EchecQualification as e: raise SystemExit(str(e)) from None
