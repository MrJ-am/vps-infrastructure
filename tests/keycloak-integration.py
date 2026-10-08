#!/usr/bin/env python3
"""Qualifier le realm versionné sur Keycloak jetable (HTTP loopback, H2).

Le conteneur de test doit démarrer avec un administrateur synthétique nommé
qualification / uniquement-test-local. Aucun accès au VPS n'est utilisé.
Prérequis : playwright, cryptography et Chromium. Le realm temporaire est
supprimé à la fin ; aucun jeton ou secret n'est affiché.
"""
import argparse
import base64
import copy
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import struct
import time
import urllib.parse
import urllib.request

from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives import hashes
from playwright.sync_api import sync_playwright

RACINE = Path(__file__).resolve().parents[1]


def decodage(valeur):
    return base64.urlsafe_b64decode(valeur + '=' * (-len(valeur) % 4))


def verifier(port, navigateur):
    assert 38000 <= port < 39000, 'Port loopback de qualification exigé.'
    base = f'http://127.0.0.1:{port}'

    def api(chemin, donnees=None, jeton=None, formulaire=False, methode=None):
        entetes = {}
        corps = None
        if donnees is not None:
            corps = (urllib.parse.urlencode(donnees) if formulaire else json.dumps(donnees)).encode()
            entetes['Content-Type'] = 'application/x-www-form-urlencoded' if formulaire else 'application/json'
        if jeton:
            entetes['Authorization'] = 'Bearer ' + jeton
        with urllib.request.urlopen(urllib.request.Request(base + chemin, corps, entetes, method=methode), timeout=20) as reponse:
            contenu = reponse.read()
            return json.loads(contenu) if contenu else None

    admin = api('/realms/master/protocol/openid-connect/token',
                {'client_id': 'admin-cli', 'username': 'qualification', 'password': 'uniquement-test-local',
                 'grant_type': 'password'}, formulaire=True)['access_token']
    version = api('/admin/serverinfo', jeton=admin)['systemInfo']['version']
    assert version == '26.7.3', 'Qualifier la version Keycloak épinglée.'
    modele = copy.deepcopy(json.loads((RACINE / 'operations/identite/realm.json').read_text()))
    realm = 'qualification-' + secrets.token_hex(6)
    modele['realm'] = realm
    secret_client = secrets.token_urlsafe(32)
    modele['clients'][0]['secret'] = secret_client
    assert not modele['registrationAllowed']
    api('/admin/realms', modele, admin)
    try:
        mot_de_passe = secrets.token_urlsafe(32)
        otp = secrets.token_urlsafe(20)
        utilisateur = 'compte-synthetique'
        api('/admin/realms/' + realm + '/users',
            {'username': utilisateur, 'enabled': True, 'emailVerified': True, 'email': 'synthetique@example.test',
             'firstName': 'Compte', 'lastName': 'Synthétique',
             'credentials': [{'type': 'password', 'value': mot_de_passe, 'temporary': False},
                             {'type': 'otp', 'secretData': json.dumps({'value': otp}),
                              'credentialData': json.dumps({'subType': 'totp', 'digits': 6, 'counter': 0,
                                                            'period': 30, 'algorithm': 'HmacSHA1'})}]}, admin)
        issuer = base + '/realms/' + realm
        protocole = '/realms/' + realm + '/protocol/openid-connect'
        retour = 'https://vision.mrj.am/auth/retour'
        preuve = secrets.token_urlsafe(48)
        nonce = secrets.token_urlsafe(32)
        etat = secrets.token_urlsafe(32)
        parametres = {'client_id': 'mrjam-vision', 'response_type': 'code', 'scope': 'openid',
                      'redirect_uri': retour, 'code_challenge_method': 'S256', 'nonce': nonce,
                      'prompt': 'login', 'max_age': '0', 'state': etat,
                      'code_challenge': base64.urlsafe_b64encode(hashlib.sha256(preuve.encode()).digest()).decode().rstrip('=')}
        with sync_playwright() as p:
            b = p.chromium.launch(**({'executable_path': navigateur} if navigateur else {}))
            try:
                page = b.new_page()
                page.route(retour + '**', lambda route: route.fulfill(status=200, body='Retour de qualification'))
                page.goto(base + protocole + '/auth?' + urllib.parse.urlencode(parametres))
                page.locator('#username').fill(utilisateur)
                page.locator('#password').fill(mot_de_passe)
                page.locator('#kc-login').click()
                page.locator('#otp').wait_for()
                compteur = struct.pack('>Q', int(time.time()) // 30)
                empreinte = hmac.new(otp.encode(), compteur, hashlib.sha1).digest()
                position = empreinte[-1] & 15
                code_otp = str((struct.unpack('>I', empreinte[position:position + 4])[0] & 0x7fffffff) % 1000000).zfill(6)
                page.locator('#otp').fill(code_otp)
                page.locator('#kc-login').click()
                page.wait_for_url(retour + '**', timeout=10000)
                reponse = urllib.parse.parse_qs(urllib.parse.urlsplit(page.url).query)
                assert reponse['state'] == [etat]
                code = reponse['code'][0]
            finally:
                b.close()
        jetons = api(protocole + '/token', {'grant_type': 'authorization_code', 'client_id': 'mrjam-vision',
                     'client_secret': secret_client, 'code': code, 'code_verifier': preuve,
                     'redirect_uri': retour}, formulaire=True)
        entete, contenu, signature = jetons['id_token'].split('.')
        entete_json = json.loads(decodage(entete))
        assert entete_json['alg'] == 'RS256'
        cle = next(c for c in api(protocole + '/certs')['keys'] if c['kid'] == entete_json['kid'])
        publique = rsa.RSAPublicNumbers(int.from_bytes(decodage(cle['e']), 'big'),
                                       int.from_bytes(decodage(cle['n']), 'big')).public_key()
        publique.verify(decodage(signature), (entete + '.' + contenu).encode(), padding.PKCS1v15(), hashes.SHA256())
        affirmations = json.loads(decodage(contenu))
        assert affirmations['iss'] == issuer and affirmations['aud'] == 'mrjam-vision'
        assert affirmations['nonce'] == nonce and affirmations['preferred_username'] == utilisateur
        assert {'pwd', 'otp'} <= set(affirmations.get('amr', []))
        maintenant = int(time.time())
        assert 0 <= maintenant - affirmations['auth_time'] < 60
        assert affirmations['iat'] <= maintenant < affirmations['exp']
        print(json.dumps({'keycloak': version, 'realm_versionne': True, 'signature_rs256': True,
                          'pkce': True, 'amr_mot_de_passe_otp': True, 'auth_time_recent': True}))
    finally:
        api('/admin/realms/' + realm, jeton=admin, methode='DELETE')


if __name__ == '__main__':
    arguments = argparse.ArgumentParser(description=__doc__)
    arguments.add_argument('--port', type=int, default=38085)
    arguments.add_argument('--navigateur', default=os.environ.get('CHROMIUM'))
    choix = arguments.parse_args()
    verifier(choix.port, choix.navigateur)
