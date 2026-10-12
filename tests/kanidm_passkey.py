"""WebAuthn réel, authentificateur virtuel Chromium, aucune identité personnelle."""
import copy
import os
import secrets
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright
from kanidm_reel import EchecQualification, KanidmLocal


def qualifier(paquet, curl):
    with KanidmLocal(paquet, curl) as n, sync_playwright() as pw:
        n.importer_une_fois()  # Compatibilité de fixture seulement, jamais propriétaire réel.
        op = n.login('idm_admin', n.recuperer('idm_admin'), privilegie=True)
        status, session = n.http('/v1/person/'+n.nom+'/_credential/_update', token=op)
        if status != 200: raise EchecQualification('session enrol passkey refusée')
        token, _ = session
        status, _ = n.http('/v1/credential/_update', ['primaryremove', token])
        if status != 200: raise EchecQualification('suppression primaire de fixture refusée')
        status, cu = n.http('/v1/credential/_update', ['passkeyinit', token])
        challenge = cu['mfaregstate']['Passkey']
        if status != 200 or challenge['publicKey']['authenticatorSelection']['userVerification'] != 'required':
            raise EchecQualification('enrôlement passkey sans UV required')
        navigateur = pw.chromium.launch(executable_path=os.environ['PLAYWRIGHT_CHROMIUM_EXECUTABLE'], headless=True)
        try:
            # Origine navigateur réelle https://log.mrj.am ; transport de test
            # intercepté vers le seul IdP local. Aucun trafic production/externe.
            context = navigateur.new_context(ignore_https_errors=True)
            hors_scope = []
            def forward(route):
                url = urlsplit(route.request.url)
                if url.hostname != 'log.mrj.am':
                    hors_scope.append(True); route.abort(); return
                response = route.fetch(url=f'https://127.0.0.1:{n.port}'+url.path+('?' + url.query if url.query else ''),
                                       headers={**route.request.all_headers(), 'Host': 'log.mrj.am'})
                route.fulfill(response=response)
            context.route('**/*', forward)
            page = context.new_page(); page.goto('https://log.mrj.am/ui/login')
            cdp = context.new_cdp_session(page); cdp.send('WebAuthn.enable', {'enableUI': False})
            authenticator = cdp.send('WebAuthn.addVirtualAuthenticator', {'options': {
                'protocol': 'ctap2', 'transport': 'internal', 'hasResidentKey': True,
                'hasUserVerification': True, 'isUserVerified': True, 'automaticPresenceSimulation': True,
            }})['authenticatorId']
            credential = page.evaluate('''async c => (await navigator.credentials.create({publicKey:
                PublicKeyCredential.parseCreationOptionsFromJSON(c.publicKey)})).toJSON()''', challenge)
            status, cu = n.http('/v1/credential/_update', [{'passkeyfinish': ['fixture-passkey', credential]}, token])
            if status != 200 or not cu['can_commit']:
                raise EchecQualification('credential navigateur refusée par IdP')
            status, _ = n.http('/v1/credential/_commit', token)
            if status != 200: raise EchecQualification('commit passkey natif refusé')

            def login(uv):
                jar=n.root/('pk-'+secrets.token_hex(8));jar.touch(mode=0o600)
                status, response=n.http('/v1/auth', {'step': {'init2': {
                    'username': n.nom, 'issue': 'token', 'privileged': False}}}, cookies=jar)
                if status != 200 or response['state'].get('choose') != ['passkey']:
                    raise EchecQualification('passkey doit être le seul mécanisme offert')
                status, response=n.http('/v1/auth', {'step': {'begin': 'passkey'}}, cookies=jar)
                request=response['state']['continue'][0]['passkey']
                if status != 200 or request['publicKey']['userVerification'] != 'required':
                    raise EchecQualification('authentification native sans UV required')
                cdp.send('WebAuthn.setUserVerified', {'authenticatorId': authenticator, 'isUserVerified': uv})
                if not uv:
                    # Client hostile : obtenir une signature valide avec UV absent.
                    # Le défi original stocké par Kanidm reste required.
                    request=copy.deepcopy(request);request['publicKey']['userVerification']='discouraged'
                assertion=page.evaluate('''async c => (await navigator.credentials.get({publicKey:
                    PublicKeyCredential.parseRequestOptionsFromJSON(c.publicKey)})).toJSON()''', request)
                status, response=n.http('/v1/auth', {'step': {'cred': {'passkey': assertion}}}, cookies=jar)
                if status != 200 or ('success' if uv else 'denied') not in response['state']:
                    raise EchecQualification('résultat de vérification UV native incorrect')

            login(True)
            n.arreter();n.demarrer();login(True)
            login(False)
            if hors_scope: raise EchecQualification('requête hors origine de fixture')
            return {'enrolement_natif': True, 'connexion_uv': True, 'passkey_apres_restart': True,
                    'mecanisme_password_absent': True, 'assertion_sans_uv_refusee': True,
                    'origine': 'https://log.mrj.am', 'authentificateur': 'virtuel Chromium',
                    'tls_certificat_synthetique_ignore_navigateur': True,
                    'enrolement_personnel_effectue': False, 'production': False}
        finally:
            navigateur.close()
