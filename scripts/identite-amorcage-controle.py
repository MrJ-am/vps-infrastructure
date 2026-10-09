"""Contrôles locaux en lecture seule ; token technique et réponses restent privés."""
import json
import re
import urllib.error
import urllib.parse
import urllib.request

URL = 'http://127.0.0.1:8085'


class SansRedirection(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def api(opener, chemin, *, token=None, formulaire=None):
    entetes = {'Host': 'log.mrj.am', 'X-Forwarded-Proto': 'https', 'X-Forwarded-Port': '443'}
    if token: entetes['Authorization'] = 'Bearer ' + token
    data = None
    if formulaire is not None:
        entetes['Content-Type'] = 'application/x-www-form-urlencoded'
        data = urllib.parse.urlencode(formulaire).encode()
    req = urllib.request.Request(URL + chemin, headers=entetes, data=data)
    with opener.open(req, timeout=10) as response:
        contenu = response.read(1048577)
        if response.code != 200 or len(contenu) > 1048576:
            raise ValueError('Contrôle privé interrompu')
        return json.loads(contenu)


def verifier(secret, realm, opener=None):
    if opener is None:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), SansRedirection())
    info = api(opener, '/realms/mrjam/.well-known/openid-configuration')
    if info.get('issuer') != 'https://log.mrj.am/realms/mrjam':
        raise ValueError('Issuer local différent')
    token = api(opener, '/realms/master/protocol/openid-connect/token', formulaire={
        'grant_type': 'password', 'client_id': 'admin-cli', 'username': 'amorcage-local', 'password': secret})['access_token']
    r = api(opener, '/admin/realms/mrjam', token=token)
    smtp = r.get('smtpServer', {}); attendu = realm.get('smtpServer', {})
    if r.get('registrationAllowed') is not False or {k:v for k,v in smtp.items() if k != 'password'} != {k:v for k,v in attendu.items() if k != 'password'} or smtp.get('password') not in (attendu.get('password'), '**********'):
        raise ValueError('Realm différent ou inscription ouverte')
    for cle in ('enabled', 'verifyEmail', 'duplicateEmailsAllowed', 'editUsernameAllowed',
            'rememberMe', 'bruteForceProtected', 'browserFlow', 'loginTheme',
            'eventsEnabled', 'eventsExpiration', 'adminEventsEnabled', 'adminEventsDetailsEnabled',
            'ssoSessionIdleTimeout', 'ssoSessionMaxLifespan', 'accessTokenLifespan'):
        if cle in realm and r.get(cle) != realm[cle]: raise ValueError('Politique d’identité différente')
    info = api(opener, '/admin/serverinfo', token=token)
    if info['systemInfo']['version'] != '26.7.3' or 'mrjam-courriel' not in info['providers']['authenticator']['providers']:
        raise ValueError('Version ou SPI différent')
    if api(opener, '/admin/realms/mrjam/users?max=2', token=token):
        raise ValueError('Personne présente avant enrôlement')
    clients = api(opener, '/admin/realms/mrjam/clients', token=token)
    attendus = {c['clientId']: c for c in realm['clients']}
    actuels = {c['clientId']: c for c in clients if c['clientId'].startswith('mrjam-')}
    if set(actuels) != set(attendus): raise ValueError('Clients techniques différents')
    for nom, modele in attendus.items():
        c = actuels[nom]
        if not re.fullmatch(r'[a-f0-9-]{36}', c['id']): raise ValueError('Identifiant technique différent')
        for cle in ('publicClient', 'serviceAccountsEnabled', 'standardFlowEnabled',
                'directAccessGrantsEnabled', 'implicitFlowEnabled', 'fullScopeAllowed'):
            if cle in modele and c.get(cle) != modele[cle]: raise ValueError('Flux client différent')
        if c.get('redirectUris', []) != modele.get('redirectUris', []) or c.get('webOrigins', []) != modele.get('webOrigins', []):
            raise ValueError('Redirections client différentes')
        if modele.get('serviceAccountsEnabled'):
            account = api(opener, '/admin/realms/mrjam/clients/' + c['id'] + '/service-account-user', token=token)
            if account.get('username') != 'service-account-' + nom:
                raise ValueError('Compte technique différent')
    return dict(import_verifie=True, aucune_personne=True, inscription_native_fermee=True,
        issuer_canonique=True, smtp_configure_sans_envoi=True, clients_fermes=True)
