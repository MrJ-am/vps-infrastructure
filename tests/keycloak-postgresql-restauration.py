"""Dump PostgreSQL 17 chiffré de l'IdP, restauration et retrait d'un sujet.

Trois conteneurs jetables, identités synthétiques et ports loopback fixes.
Ne fournit aucune option visant une instance ou une base de production.
"""
import argparse
import base64
import hashlib
import hmac
import importlib.util
import json
import os
from pathlib import Path
import secrets
import struct
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from playwright.sync_api import sync_playwright

RACINE = Path(__file__).resolve().parents[1]
IMAGE = 'quay.io/keycloak/keycloak:26.7.3@sha256:29be7252db0a106f1cd2ac17b9a56ff2668073da645638a38b9fc67deeb2d6c4'


def commande(*args, entree=None):
    r = subprocess.run(args, input=entree, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if r.returncode:
        raise RuntimeError('Commande de qualification refusée : ' + Path(args[0]).name)
    return r.stdout


def api(port, path, donnees=None, methode=None, jeton=None, formulaire=False):
    entetes = {}; corps = None
    if donnees is not None:
        corps = (urllib.parse.urlencode(donnees) if formulaire else json.dumps(donnees)).encode()
        entetes['Content-Type'] = 'application/x-www-form-urlencoded' if formulaire else 'application/json'
    if jeton: entetes['Authorization'] = 'Bearer ' + jeton
    with urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{port}' + path, corps, entetes, method=methode), timeout=10) as r:
        contenu = r.read(); return json.loads(contenu) if contenu else None


def administrateur(port):
    return api(port, '/realms/master/protocol/openid-connect/token',
        dict(client_id='admin-cli', username='qualification', password='uniquement-test-local', grant_type='password'),
        formulaire=True)['access_token']


def attendre(port):
    for _ in range(60):
        try:
            api(port, '/realms/master/.well-known/openid-configuration'); return
        except (OSError, urllib.error.HTTPError): time.sleep(1)
    raise RuntimeError('Identité PostgreSQL de qualification indisponible')


def verifier(jar, navigateur):
    assert jar.is_file()
    nom = 'qualification-idp-' + uuid.uuid4().hex[:12]
    pg = nom + '-pg'; original = nom + '-original'; restaure = nom + '-restaure'
    try:
        commande('docker', 'run', '-d', '--name', pg, '--network', 'host',
            '-e', 'POSTGRES_PASSWORD=uniquement-test-local-db', '-e', 'POSTGRES_DB=identite_source',
            'pgvector/pgvector:0.8.0-pg17', '-p', '35434', '-c', 'listen_addresses=127.0.0.1')
        for _ in range(30):
            try:
                commande('docker', 'exec', pg, 'pg_isready', '-U', 'postgres', '-p', '35434'); break
            except RuntimeError: time.sleep(1)
        else: raise RuntimeError('PostgreSQL synthétique indisponible')

        def demarrer(conteneur, base, port):
            commande('docker', 'run', '-d', '--name', conteneur, '--network', 'host',
                '-v', str(jar) + ':/opt/keycloak/providers/mrjam-identite.jar:ro',
                '-v', str(RACINE / 'services/keycloak-mrjam/theme') + ':/opt/keycloak/themes/mrjam:ro',
                '-e', 'KC_DB=postgres', '-e', 'KC_DB_URL=jdbc:postgresql://127.0.0.1:35434/' + base,
                '-e', 'KC_DB_USERNAME=postgres', '-e', 'KC_DB_PASSWORD=uniquement-test-local-db',
                '-e', 'KC_BOOTSTRAP_ADMIN_USERNAME=qualification', '-e', 'KC_BOOTSTRAP_ADMIN_PASSWORD=uniquement-test-local',
                IMAGE, 'start-dev', '--http-host=127.0.0.1', '--http-port=' + str(port))
            attendre(port)

        demarrer(original, 'identite_source', 38088)
        admin = administrateur(38088)
        realm = 'qualification-restauration-' + uuid.uuid4().hex[:12]
        sujet = str(uuid.uuid4()); mot_de_passe = secrets.token_urlsafe(32); otp = secrets.token_urlsafe(20)
        retour = 'http://127.0.0.1:38999/retour'
        api(38088, '/admin/realms', {'realm': realm, 'enabled': True,
            'clients': [{'clientId': 'qualification-restauration', 'publicClient': True,
                'standardFlowEnabled': True, 'redirectUris': [retour]}],
            'users': [{'id': sujet, 'username': 'synthetique', 'email': 'synthetique@example.test',
                'firstName': 'Compte', 'lastName': 'Synthétique', 'emailVerified': True, 'enabled': True,
                'credentials': [{'type': 'password', 'value': mot_de_passe, 'temporary': False},
                    {'type': 'otp', 'secretData': json.dumps({'value': otp}),
                        'credentialData': json.dumps(dict(subType='totp', digits=6, counter=0, period=30, algorithm='HmacSHA1'))}]}]}, jeton=admin)
        profil = api(38088, '/admin/realms/' + realm + '/users/' + sujet, jeton=admin)
        with tempfile.TemporaryDirectory() as root:
            root = Path(root); cle = root / 'restauration.age'; chiffre = root / 'identite.dump.age'; clair = root / 'restauration.dump'
            commande('age-keygen', '-o', str(cle))
            recipient = commande('age-keygen', '-y', str(cle)).decode().strip()
            dump = commande('docker', 'exec', pg, 'pg_dump', '-Fc', '-U', 'postgres', '-p', '35434', 'identite_source')
            assert dump.startswith(b'PGDMP')
            commande('age', '-r', recipient, '-o', str(chiffre), entree=dump); del dump
            commande('age', '-d', '-i', str(cle), '-o', str(clair), str(chiffre))
            commande('docker', 'exec', pg, 'createdb', '-U', 'postgres', '-p', '35434', 'identite_restauration')
            commande('docker', 'exec', '-i', pg, 'pg_restore', '--no-owner', '--exit-on-error',
                '-U', 'postgres', '-p', '35434', '-d', 'identite_restauration', entree=clair.read_bytes())
            clair.unlink()
            demarrer(restaure, 'identite_restauration', 38089)
            copie = api(38089, '/admin/realms/' + realm + '/users/' + sujet, jeton=administrateur(38089))
            assert copie['id'] == profil['id'] and copie['emailVerified'] and copie['enabled']
            # Le mot de passe et l'OTP restaurés doivent ouvrir le parcours natif.
            preuve = secrets.token_urlsafe(48)
            parametres = dict(client_id='qualification-restauration', response_type='code', scope='openid',
                redirect_uri=retour, code_challenge_method='S256', state=secrets.token_urlsafe(32),
                code_challenge=base64.urlsafe_b64encode(hashlib.sha256(preuve.encode()).digest()).decode().rstrip('='))
            with sync_playwright() as p:
                b = p.chromium.launch(**({'executable_path': navigateur} if navigateur else {}))
                try:
                    page = b.new_page(); page.route(retour + '**', lambda route: route.fulfill(status=200, body='Qualification'))
                    page.goto('http://127.0.0.1:38089/realms/' + realm + '/protocol/openid-connect/auth?' + urllib.parse.urlencode(parametres))
                    page.locator('#username').fill('synthetique'); page.locator('#password').fill(mot_de_passe)
                    page.locator('#kc-login').click(); page.locator('#otp').wait_for()
                    empreinte = hmac.new(otp.encode(), struct.pack('>Q', int(time.time()) // 30), hashlib.sha1).digest()
                    position = empreinte[-1] & 15
                    code = str((struct.unpack('>I', empreinte[position:position + 4])[0] & 0x7fffffff) % 1000000).zfill(6)
                    page.locator('#otp').fill(code); page.locator('#kc-login').click(); page.wait_for_url(retour + '**')
                    assert urllib.parse.parse_qs(urllib.parse.urlsplit(page.url).query)['state'] == [parametres['state']]
                finally: b.close()
            config = root / 'identite.json'
            config.write_text(json.dumps(dict(version=1, base_isolee='http://127.0.0.1:38089', realm=realm,
                utilisateur='qualification', mot_de_passe='uniquement-test-local'))); config.chmod(0o600)
            spec = importlib.util.spec_from_file_location('rejeu', RACINE / 'scripts/vision-effacements-rejouer.py')
            module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
            module.effacer_identites({sujet}, config); module.effacer_identites({sujet}, config)
            try:
                api(38089, '/admin/realms/' + realm + '/users/' + sujet, jeton=administrateur(38089))
                raise AssertionError('Sujet réintroduit dans la restauration')
            except urllib.error.HTTPError as e: assert e.code == 404
            assert api(38088, '/admin/realms/' + realm + '/users/' + sujet, jeton=administrateur(38088))['id'] == sujet
        print(json.dumps(dict(idp_postgresql17_restaure=True, age_reel=True, sujet_stable=True,
            mot_de_passe_et_otp_restaures=True, effacement_rejoue_deux_fois=True, source_preservee=True,
            jdbc_unix_production=False)))
    finally:
        for conteneur in (restaure, original, pg):
            subprocess.run(['docker', 'rm', '-f', conteneur], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--jar', type=Path, required=True)
    p.add_argument('--navigateur', default=os.environ.get('CHROMIUM')); a = p.parse_args()
    verifier(a.jar.resolve(), a.navigateur)
