"""Qualification d'un Kanidm officiel local, données entièrement synthétiques.

Les sorties d'authentification et sauvegardes restent en mémoire ou dans un
répertoire privé éphémère. Aucun accès réseau autre que loopback.
"""
from contextlib import AbstractContextManager
import gzip
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import tempfile
import time
import uuid
from urllib.parse import urlencode, urlsplit, parse_qs


class EchecQualification(RuntimeError):
    """Diagnostic sans corps HTTP, token, mot de passe ou empreinte privée."""


class KanidmLocal(AbstractContextManager):
    def __init__(self, paquet, curl, rounds=5000):
        self.paquet = Path(paquet).resolve()
        self.curl = Path(curl).resolve()
        if not str(self.paquet).startswith('/nix/store/'):
            raise EchecQualification('paquet officiel Nix requis')
        for outil in (self.paquet/'bin/kanidmd', self.paquet/'bin/kanidm', self.curl):
            if not outil.is_file():
                raise EchecQualification('exécutable déjà installé requis')
        self.processus = None
        if rounds not in (5000, 656000):
            raise EchecQualification('paramètre fixture rounds inconnu')
        self.rounds = rounds

    def commande(self, *args):
        result = subprocess.run([str(self.paquet/'bin/kanidmd'), '-c', str(self.config), *args],
                                capture_output=True, text=True, timeout=45)
        if result.returncode:
            raise EchecQualification('commande native refusée : ' + args[0])
        return result.stdout

    def __enter__(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mrjam-kanidm-reel-')
        self.root = Path(self.temp.name)
        self.root.chmod(0o700)
        self.config = self.root/'server.toml'
        self.ca = self.root/'chain.pem'
        self.migrations = self.root/'migrations'; self.migrations.mkdir(mode=0o700)
        self.uuid = str(uuid.uuid4())
        self.nom = 'fixture-vision'
        self.mail = 'fixture-vision@example.test'
        self.password = 'Synthese-' + secrets.token_urlsafe(32)
        args = ['openssl', 'passwd', '-6', '-stdin']
        if self.rounds == 656000: args += ['-salt', 'rounds=656000$selSynthese']
        self.hashed = subprocess.run(args, input=self.password+'\n',
                                    capture_output=True, text=True, check=True).stdout.strip()
        if not self.hashed.startswith('$6$'):
            raise EchecQualification('fixture SHA512-crypt incorrecte')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); self.port = sock.getsockname()[1]
        self.config.write_text('\n'.join([
            'version = "2"', 'domain = "log.mrj.am"', 'origin = "https://log.mrj.am"',
            f'bindaddress = "127.0.0.1:{self.port}"', f'db_path = "{self.root}/kanidm.db"',
            f'tls_chain = "{self.ca}"', f'tls_key = "{self.root}/key.pem"',
            f'adminbindpath = "{self.root}/admin.sock"',
            f'migration_path = "{self.migrations}"', 'log_level = "info"', 'thread_count = 2',
        ]) + '\n'); self.config.chmod(0o600)
        try:
            self.commande('cert-generate')
            for path in self.root.glob('*.pem'): path.chmod(0o600)
            self.log = (self.root/'serveur.log').open('w'); os.chmod(self.log.name, 0o600)
            self.demarrer()
            return self
        except BaseException:
            self.__exit__(True, None, None)
            raise

    def demarrer(self):
        if self.processus and self.processus.poll() is None:
            raise EchecQualification('serveur synthétique déjà actif')
        self.processus = subprocess.Popen([str(self.paquet/'bin/kanidmd'), '-c', str(self.config), 'server'],
                                          stdout=self.log, stderr=self.log, umask=0o077)
        for _ in range(100):
            if self.processus.poll() is not None:
                raise EchecQualification('serveur natif arrêté au démarrage')
            try:
                status, _ = self.http('/status')
                if status == 200 and (self.root/'admin.sock').exists(): return
            except EchecQualification:
                pass
            time.sleep(0.2)
        raise EchecQualification('démarrage natif hors délai')

    def arreter(self):
        if self.processus and self.processus.poll() is None:
            self.processus.terminate()
            try: self.processus.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.processus.kill(); self.processus.wait(timeout=5)

    def http(self, chemin, document=None, *, token=None, cookies=None, method=None, headers=False):
        if not chemin.startswith('/') or any(c in chemin for c in '\r\n"\\'):
            raise EchecQualification('chemin fixture invalide')
        # Toute donnée sensible passe par stdin, jamais argv ou environnement.
        def quoted(value):
            if any(ord(c) < 32 or ord(c) == 127 for c in value):
                raise EchecQualification('contrôle dans option curl')
            return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'
        options = ['silent', 'show-error', 'max-time = 5', 'proxy = ""', 'proto = "=https"',
                   'max-filesize = 1048576', 'tlsv1.2',
                   'url = ' + quoted('https://log.mrj.am' + chemin),
                   'connect-to = ' + quoted(f'log.mrj.am:443:127.0.0.1:{self.port}'),
                   'cacert = ' + quoted(str(self.ca)), 'write-out = "\\n%{response_code}"']
        if cookies:
            options += ['cookie = ' + quoted(str(cookies)), 'cookie-jar = ' + quoted(str(cookies))]
        if token:
            options += ['header = ' + quoted('Authorization: Bearer ' + token)]
        if method:
            if method not in ('GET', 'POST', 'PUT', 'PATCH', 'DELETE'):
                raise EchecQualification('méthode fixture inconnue')
            options += ['request = ' + quoted(method)]
        headerfile = None
        if headers:
            headerfile = self.root/('headers-' + secrets.token_hex(8))
            headerfile.touch(mode=0o600)
            options += ['dump-header = ' + quoted(str(headerfile))]
        if document is not None:
            options += ['header = "Content-Type: application/json"', 'request = ' + quoted(method or 'POST'),
                        'data = ' + quoted(json.dumps(document))]
        result = subprocess.run([str(self.curl), '--disable', '--config', '-'],
                                input='\n'.join(options)+'\n', capture_output=True, text=True,
                                timeout=8, umask=0o077)
        if result.returncode:
            raise EchecQualification('transport HTTPS natif refusé')
        try:
            body, status = result.stdout.rsplit('\n', 1)
            result = (int(status), json.loads(body) if body else None)
            if headerfile:
                hs = {}
                for line in headerfile.read_text().splitlines():
                    if ':' in line:
                        name, value = line.split(':', 1); name = name.lower()
                        if name == 'location' and name in hs:
                            raise EchecQualification('retour natif ambigu')
                        hs[name] = value.strip()
                return (*result, hs)
            return result
        except (ValueError, json.JSONDecodeError):
            raise EchecQualification('réponse native non JSON') from None

    def recuperer(self, nom):
        try:
            result = json.loads(self.commande('scripting', 'recover-account', nom))
            assert result['status'] == 'ok' and isinstance(result['output'], str)
            return result['output']
        except (ValueError, KeyError, AssertionError):
            raise EchecQualification('récupération native invalide') from None

    def importer_une_fois(self):
        """API officielle de migration, finalisée immédiatement, sans passerelle."""
        admin = self.login('admin', self.recuperer('admin'), privilegie=True)
        self.admin = admin  # Uniquement fixture opérateur ; jamais transmis au client Lisp.
        nom = 'fixture-import-vision'
        status, _ = self.http('/v1/sync_account', {'attrs': {'name': [nom]}}, token=admin)
        if status != 200: raise EchecQualification(f'création import ponctuel refusée (HTTP{status})')
        status, jeton = self.http('/v1/sync_account/' + nom + '/_sync_token', 'fixture-ponctuelle', token=admin)
        if status != 200 or not isinstance(jeton, str):
            raise EchecQualification('capacité import ponctuel non créée')
        payload = {'from_state': 'Refresh', 'to_state': {'Active': {'cookie': 'AA'}},
                   'retain': 'Ignore', 'entries': [{
                       'schemas': ['urn:ietf:params:scim:schemas:kanidm:sync:1:person',
                                   'urn:ietf:params:scim:schemas:kanidm:sync:1:account'],
                       'id': self.uuid, 'externalId': 'fixture-vision', 'name': self.nom,
                       'displayname': 'Fixture Vision', 'mail': [{'value': self.mail, 'primary': True}],
                       'password_import': '{crypt}' + self.hashed,
                   }]}
        status, _ = self.http('/scim/v1/Sync', payload, token=jeton)
        if status != 200: raise EchecQualification(f'import SCIM officiel refusé (HTTP{status})')
        # Finalise conserve les comptes importés. Terminate les effacerait : jamais appelé.
        status, _ = self.http('/v1/sync_account/' + nom + '/_finalise', token=admin)
        if status != 200: raise EchecQualification(f'finalisation import refusée (HTTP{status})')
        status, _ = self.http('/scim/v1/Sync', token=jeton)
        if status not in (401, 403):
            raise EchecQualification('capacité import toujours active après finalisation')

    def creer_client_oidc(self, client='mrjam-vision', hote='vision.mrj.am'):
        operateur = self.login('idm_admin', self.recuperer('idm_admin'), privilegie=True)
        status, _ = self.http('/v1/oauth2/_basic', {'attrs': {
            'name': [client], 'displayname': ['Fixture OIDC'],
            'oauth2_rs_origin_landing': ['https://' + hote], 'oauth2_strict_redirect_uri': ['true'],
        }}, token=operateur)
        if status != 200: raise EchecQualification(f'client OIDC natif refusé (HTTP{status})')
        for chemin, document in (
            ('/v1/oauth2/'+client+'/_attr/oauth2_rs_origin', ['https://'+hote+'/auth/retour']),
            ('/v1/oauth2/'+client+'/_scopemap/idm_all_persons', ['openid', 'profile', 'email']),
        ):
            status, _ = self.http(chemin, document, token=operateur)
            if status != 200: raise EchecQualification(f'contrat client OIDC refusé (HTTP{status})')
        status, secret = self.http('/v1/oauth2/'+client+'/_basic_secret', token=operateur)
        if status != 200 or not isinstance(secret, str):
            raise EchecQualification('secret client natif absent')
        return secret

    def autoriser_code(self, token, client, hote, state, nonce, challenge):
        params = {'client_id': client, 'response_type': 'code', 'redirect_uri': 'https://'+hote+'/auth/retour',
                  'scope': 'openid profile email', 'state': state, 'nonce': nonce,
                  'code_challenge': challenge, 'code_challenge_method': 'S256'}
        status, response, hs = self.http('/oauth2/authorise?'+urlencode(params), token=token, headers=True)
        if status == 200 and isinstance(response, dict) and 'ConsentRequested' in response:
            consent = response['ConsentRequested']['consent_token']
            status, _, hs = self.http('/oauth2/authorise/permit', consent, token=token, headers=True)
        if status not in (200, 302) or 'location' not in hs:
            raise EchecQualification(f'autorisation OIDC native non aboutie (HTTP{status})')
        uri = urlsplit(hs['location']); query = parse_qs(uri.query, strict_parsing=True)
        if uri.scheme != 'https' or uri.netloc != hote or uri.path != '/auth/retour' or query.get('state') != [state] or len(query.get('code', [])) != 1:
            raise EchecQualification('retour ou state OIDC natif divergent')
        return query['code'][0]

    def algorithme_password(self):
        backup = self.root/('backup-' + secrets.token_hex(8))
        self.commande('scripting', 'backup', str(backup))
        if not backup.is_file():
            raise EchecQualification('sauvegarde native absente')
        backup.chmod(0o600)
        data = backup.read_bytes()
        if data.startswith(b'\x1f\x8b'): data = gzip.decompress(data)
        if len(data) > 32*1024*1024:
            raise EchecQualification('sauvegarde fixture hors borne')
        document = json.loads(data)
        for entry in document['entries']:
            attrs = entry['ent']['V3']['attrs']
            if attrs.get('uuid', {}).get('UU') == [self.uuid]:
                if 'sync_parent_uuid' in attrs or 'syncobject' in attrs.get('class', {}).get('I8', []):
                    raise EchecQualification('propriétaire encore rattaché à une synchronisation')
                # Lecture du stockage synthétique pour prouver le réhachage réel.
                # Le matériel secret reste en mémoire, seul le nom est retourné.
                credentials = attrs.get('primary_credential', {}).get('CR', [])
                if len(credentials) != 1:
                    raise EchecQualification('credential synthétique absent ou ambigu')
                password = credentials[0]['d']['password']
                if len(password) != 1:
                    raise EchecQualification('format password natif ambigu')
                return next(iter(password))
        raise EchecQualification('propriétaire absent de la sauvegarde native')

    def login(self, nom, password, *, privilegie=False, refus=False):
        cookies = self.root/('cookies-' + secrets.token_hex(8))
        cookies.touch(mode=0o600)
        sequence = [
            {'step': {'init2': {'username': nom, 'issue': 'token', 'privileged': privilegie}}},
            {'step': {'begin': 'password'}}, {'step': {'cred': {'password': password}}},
        ]
        for index, request in enumerate(sequence):
            status, response = self.http('/v1/auth', request, cookies=cookies)
            if status != 200 or not isinstance(response, dict):
                raise EchecQualification('étape de connexion native refusée')
            state = response.get('state', {})
            expected = ('choose', 'continue', 'denied' if refus else 'success')[index]
            if expected not in state:
                raise EchecQualification('mécanisme ou résultat de connexion natif inattendu')
        return None if refus else state['success']

    def __exit__(self, erreur, *_):
        self.arreter()
        if hasattr(self, 'log'): self.log.close()
        if erreur and (self.root/'serveur.log').exists():
            # Diagnostic local privé, jamais recopié dans la sortie de la suite.
            dest = Path(__file__).resolve().parents[1]/'state/kanidm-echec-native.log'
            fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, 'wb') as out:
                out.write((self.root/'serveur.log').read_bytes())
        if hasattr(self, 'temp'): self.temp.cleanup()


def qualifier_import(paquet, curl, rounds=5000):
    with KanidmLocal(paquet, curl, rounds) as natif:
        natif.importer_une_fois()
        if natif.algorithme_password() != 'CRYPT_SHA512':
            raise EchecQualification('import SHA512-crypt non appliqué')
        token = natif.login(natif.nom, natif.password)
        if not token: raise EchecQualification('import sans connexion effective')
        status, personne = natif.http('/v1/person/' + natif.nom, token=token)
        if status != 200 or personne['attrs']['uuid'] != [natif.uuid] or personne['attrs']['mail'] != [natif.mail]:
            raise EchecQualification('propriétaire ou email natif divergent')
        for _ in range(10):
            if natif.algorithme_password() == 'ARGON2ID': break
            time.sleep(0.2)
        else: raise EchecQualification('réhachage Argon2id natif non constaté')
        ancien_pid = natif.processus.pid
        natif.arreter(); natif.demarrer()
        if natif.processus.pid == ancien_pid or natif.algorithme_password() != 'ARGON2ID':
            raise EchecQualification('réhachage non persistant après redémarrage')
        status, personne = natif.http('/v1/person/' + natif.nom, token=token)
        if status != 200 or personne['attrs']['uuid'] != [natif.uuid]:
            raise EchecQualification('session native perdue au redémarrage')
        natif.login(natif.nom, natif.password)
        natif.login(natif.nom, natif.password + '-incorrect', refus=True)
        return {'serveur_reel': True, 'tls_verifie': True, 'uuid_conserve': True,
                'email_conserve': True, 'sha512_crypt_login': True, 'mauvais_password_refuse': True,
                'argon2id_verifie': True, 'restart_sans_fichier_import': True,
                'session_conservee_au_restart': True, 'import_ponctuel_finalise': True,
                'capacite_import_revoquee': True, 'production': False}


def constater_limite_import(paquet, curl):
    """Régression amont observée : rechargement avant premier login, sans patch."""
    with KanidmLocal(paquet, curl) as natif:
        natif.importer_une_fois()
        if natif.algorithme_password() != 'CRYPT_SHA512':
            raise EchecQualification('fixture de régression import non établie')
        natif.arreter(); natif.demarrer()
        if natif.algorithme_password() != 'CRYPT_SHA512':
            raise EchecQualification('stockage importé modifié au restart')
        # L'auth accepte le mécanisme Password mais refuse le bon mot de passe.
        # Ce résultat est une limite bloquante pour l'import, jamais une migration réussie.
        natif.login(natif.nom, natif.password, refus=True)
        return {'defaut_reload_sha512_crypt_observe': True,
                'import_password_retenu_production': False,
                'choix_proprietaire': 'nouvelle_identite_avec_donnees_Vision_preservees'}


class FixtureOIDC(KanidmLocal):
    def __enter__(self):
        super().__enter__()
        try:
            self.importer_une_fois()
            secret = self.creer_client_oidc()
            user = self.login(self.nom, self.password)
            verifier = secrets.token_urlsafe(32)
            state = secrets.token_urlsafe(32); nonce = secrets.token_urlsafe(32)
            challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
            code = self.autoriser_code(user, 'mrjam-vision', 'vision.mrj.am', state, nonce, challenge)
            response = self.root/'reponse-jetons.json'; response.touch(mode=0o600)
            self.path = self.root/'oidc-fixture.json'
            self.path.write_text(json.dumps({'secret': secret, 'port': self.port, 'ca': str(self.ca),
                                            'code': code, 'verifier': verifier, 'nonce': nonce,
                                            'uuid': self.uuid, 'maintenant': int(time.time()),
                                            'curl': str(self.curl), 'reponse': str(response)}))
            self.path.chmod(0o600)
            return self
        except BaseException:
            self.__exit__(True, None, None)
            raise
