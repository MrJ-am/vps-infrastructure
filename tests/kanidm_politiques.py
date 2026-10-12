"""Politiques/enrôlement natifs sur données synthétiques privées.

Le calcul RFC6238 de fixture utilise seulement hmac/hashlib de Python ;
le secret est généré et vérifié par Kanidm, jamais par le produit métier.
"""
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import struct
import time

from kanidm_reel import EchecQualification, KanidmLocal


def code_totp(secret):
    if secret['algo'] != 'sha256':
        raise EchecQualification('fixture native TOTP doit utiliser SHA256, sans compatibilité SHA1')
    digest = hmac.new(bytes(secret['secret']), struct.pack('>Q', int(time.time())//secret['step']),
                      hashlib.sha256).digest()
    offset = digest[-1] & 15
    return (int.from_bytes(digest[offset:offset+4], 'big') & 0x7fffffff) % 10**secret['digits']


def login_mfa(natif, secret):
    jar = natif.root/('mfa-cookies-' + secrets.token_hex(8)); jar.touch(mode=0o600)
    status, response = natif.http('/v1/auth', {'step': {'init2': {
        'username': natif.nom, 'issue': 'token', 'privileged': False}}}, cookies=jar)
    if status != 200 or response.get('state', {}).get('choose') != ['passwordmfa']:
        raise EchecQualification('MFA doit être le seul mécanisme offert')
    requests = [({'step': {'begin': 'passwordmfa'}}, 'continue'),
                ({'step': {'cred': {'totp': code_totp(secret)}}}, 'continue'),
                ({'step': {'cred': {'password': natif.password}}}, 'success')]
    for request, expected in requests:
        status, response = natif.http('/v1/auth', request, cookies=jar)
        if status != 200 or expected not in response.get('state', {}):
            raise EchecQualification('authentification MFA réelle incomplète')
    return response['state']['success']


def qualifier(paquet, curl):
    nombre = 0
    with KanidmLocal(paquet, curl) as n:
        n.importer_une_fois()  # Fixture seulement ; import SHA512 interdit en production.
        op = n.login('idm_admin', n.recuperer('idm_admin'), privilegie=True)
        status, session = n.http('/v1/person/'+n.nom+'/_credential/_update', token=op)
        if status != 200: raise EchecQualification('enrôlement natif refusé')
        token, _ = session
        status, cu = n.http('/v1/credential/_update', [{'password': n.password}, token])
        if status != 200 or cu['can_commit'] or 'MfaRequired' not in cu['warnings']:
            raise EchecQualification('minimum MFA doit empêcher le commit password seul')
        nombre += 3
        status, cu = n.http('/v1/credential/_update', ['totpgenerate', token])
        if status != 200 or 'TotpCheck' not in cu['mfaregstate']:
            raise EchecQualification('enrôlement TOTP natif non démarré')
        secret = cu['mfaregstate']['TotpCheck']
        nombre += 2
        status, cu = n.http('/v1/credential/_update', [{'totpverify': [code_totp(secret), 'fixture-totp']}, token])
        if status != 200 or not cu['can_commit']:
            raise EchecQualification('preuve TOTP refusée par IdP réel')
        nombre += 2
        status, _ = n.http('/v1/credential/_commit', token)
        if status != 200: raise EchecQualification('commit MFA refusé')
        nombre += 1
        # La modification Canonique stocke Argon2id et enlève le mécanisme faible.
        if n.algorithme_password() != 'ARGON2ID':
            raise EchecQualification('enrôlement password natif non durable')
        login_mfa(n, secret); nombre += 5
        n.arreter(); n.demarrer()
        login_mfa(n, secret); nombre += 5

        # Deux politiques globales imposent le minimum, pas seulement all_persons.
        def mutation(chemin, document, method=None):
            status, _ = n.http(chemin, document, token=op, method=method)
            if status != 200: raise EchecQualification('politique de fixture refusée')

        mutation('/v1/group', {'attrs': {'name': ['fixture-duree']}})
        mutation('/v1/group/fixture-duree/_attr/class', ['account_policy'])
        mutation('/v1/group/fixture-duree/_attr/member', [n.nom])
        mutation('/v1/group/fixture-duree/_attr/authsession_expiry', ['604800'], 'PUT')
        mutation('/v1/group/idm_all_persons/_attr/authsession_expiry', ['7776000'], 'PUT')

        def duree_auth():
            # Décodage de token émis sur TLS par cet IdP de fixture seulement.
            # Ne constitue pas un vérificateur de token utilisé par le produit.
            import base64
            t = login_mfa(n, secret)
            payload = json.loads(base64.urlsafe_b64decode(t.split('.')[1]+'=='))
            return payload['expiry'] - payload['issued_at']

        if duree_auth() != 86400:
            raise EchecQualification('précondition défaut all_accounts24h non constatée')
        nombre += 1
        mutation('/v1/group/idm_all_accounts/_attr/authsession_expiry', ['7776000'], 'PUT')
        for jours in (7, 30, 90):
            mutation('/v1/group/fixture-duree/_attr/authsession_expiry', [str(jours*86400)], 'PUT')
            if duree_auth() != jours*86400:
                raise EchecQualification('durée native effective différente du profil')
            nombre += 1
        # Une contrainte de rôle ne raccourcit que la personne membre.
        mutation('/v1/group', {'attrs': {'name': ['fixture-role']}})
        mutation('/v1/group/fixture-role/_attr/class', ['account_policy'])
        mutation('/v1/group/fixture-role/_attr/member', [n.nom])
        mutation('/v1/group/fixture-role/_attr/authsession_expiry', ['604800'], 'PUT')
        if duree_auth() != 604800:
            raise EchecQualification('contrainte plus forte de rôle non effective')
        nombre += 1
        return {'assertions': nombre, 'mfa_password_totp_sha256': True,
                'password_simple_absent_apres_enrolement': True, 'mfa_apres_restart': True,
                'profils_jours_effectifs': [7, 30, 90], 'contrainte_role_jours': 7,
                'minima_deux_defauts_verifies': True, 'production': False,
                'limites': ['Enrôlement utilisateur personnel non effectué.',
                            'Passkeys/navigateurs et médiation de préférences individuelles non qualifiés.']}
