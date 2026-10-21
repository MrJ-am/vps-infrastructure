"""Renommage réel en Kanidm 1.11.2 officiel isolé, passkey Chromium synthétique."""
import importlib.util
import json
import os
from pathlib import Path
import secrets
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from kanidm_reel import KanidmLocal
from kanidm_politiques import creer_neuf_mfa
from playwright.sync_api import sync_playwright

spec = importlib.util.spec_from_file_location('rename_log', ROOT / 'scripts/log-identite-renommer.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class Native(KanidmLocal):
    def __init__(self):
        # Binaire extrait du conteneur officiel à digest figé, sans modifier
        # le produit Nix ni prétendre qualifier sa construction.
        self.paquet = Path(os.environ['KANIDM_TEST_PACKAGE'])
        self.curl = Path('/usr/bin/curl')
        self.processus = None
        self.rounds = 5000

    def commande(self, *args):
        if args[0] == 'cert-generate':
            with self.config.open('a') as f:
                f.write('role = "WriteReplicaNoUI"\n')
        return super().commande(*args)


class Api:
    def __init__(self, natif):
        self.n = natif

    def http(self, path, body=None, *, token=None, method=None, attendu=200):
        status, result = self.n.http(path, body, token=token, method=method)
        if status != attendu:
            raise ValueError('HTTP' + str(status))
        return result


@unittest.skipUnless(os.environ.get('KANIDM_TEST_PACKAGE'), 'Binaire natif officiel requis')
class RenommageNatif(unittest.TestCase):
    def test_nom_reel_passkey_sessions_uuid_et_conflit(self):
        with Native() as n, sync_playwright() as p:
            creer_neuf_mfa(n)
            op = n.login('idm_admin', n.recuperer('idm_admin'), privilegie=True)
            status, session = n.http('/v1/person/' + n.uuid + '/_credential/_update', token=op)
            self.assertEqual(status, 200)
            capability = session[0]
            self.assertEqual(n.http('/v1/credential/_update', ['primaryremove', capability])[0], 200)
            status, cu = n.http('/v1/credential/_update', ['passkeyinit', capability])
            self.assertEqual(status, 200)
            browser = p.chromium.launch(executable_path='/usr/bin/chromium', headless=True, args=['--no-sandbox'])
            try:
                context = browser.new_context()
                # Origine WebAuthn synthétique ; aucune requête ne sort de la fixture.
                context.route('**/*', lambda route: route.fulfill(status=200, content_type='text/html', body='<title>Fixture</title>'))
                page = context.new_page()
                page.goto('https://log.mrj.am/')
                cdp = context.new_cdp_session(page)
                cdp.send('WebAuthn.enable', {'enableUI': False})
                cdp.send('WebAuthn.addVirtualAuthenticator', {'options': {
                    'protocol': 'ctap2', 'transport': 'internal', 'hasResidentKey': True,
                    'hasUserVerification': True, 'isUserVerified': True, 'automaticPresenceSimulation': True}})
                cred = page.evaluate('''async c => (await navigator.credentials.create({publicKey:
                    PublicKeyCredential.parseCreationOptionsFromJSON(c.publicKey)})).toJSON()''', cu['mfaregstate']['Passkey'])
                status, cu = n.http('/v1/credential/_update', [{'passkeyfinish': ['fixture', cred]}, capability])
                self.assertEqual(status, 200)
                self.assertTrue(cu['can_commit'])
                self.assertEqual(n.http('/v1/credential/_commit', capability)[0], 200)

                def passkey_login(nom):
                    jar = n.root / ('auth-' + secrets.token_hex(8)); jar.touch(mode=0o600)
                    status, response = n.http('/v1/auth', {'step': {'init2': {
                        'username': nom, 'issue': 'token', 'privileged': False}}}, cookies=jar)
                    self.assertEqual((status, response['state'].get('choose')), (200, ['passkey']))
                    status, response = n.http('/v1/auth', {'step': {'begin': 'passkey'}}, cookies=jar)
                    self.assertEqual(status, 200)
                    assertion = page.evaluate('''async c => (await navigator.credentials.get({publicKey:
                        PublicKeyCredential.parseRequestOptionsFromJSON(c.publicKey)})).toJSON()''', response['state']['continue'][0]['passkey'])
                    status, response = n.http('/v1/auth', {'step': {'cred': {'passkey': assertion}}}, cookies=jar)
                    self.assertEqual(status, 200)
                    self.assertIn('success', response['state'])
                    return response['state']['success']

                ancien = n.nom
                session_avant = passkey_login(ancien)
                # Le propriétaire de production est lui aussi protégé de la délégation.
                sysop = n.login('admin', n.recuperer('admin'), privilegie=True)
                self.assertEqual(n.http('/v1/group/idm_high_privilege/_attr/member', [n.uuid], token=sysop)[0], 200)
                api = Api(n)
                # Conflit réel : un second compte ne doit jamais être fusionné/écrasé.
                self.assertEqual(n.http('/v1/person', {'attrs': {'name': ['fixture-occupee'], 'displayname': ['Autre']}}, token=op)[0], 200)
                with self.assertRaises(ValueError):
                    m.renommer(api, n.uuid, ancien, 'fixture-occupee', op)
                self.assertEqual(n.http('/v1/person/' + n.uuid, token=op)[1]['attrs']['name'], [ancien])
                result = m.renommer(api, n.uuid, ancien, 'Fixture-Renommee', op)
                self.assertTrue(result['ancien_nom_retire'])
                self.assertTrue(result['uuid_et_credentials_sessions_preserves'])
                self.assertEqual(n.http('/v1/person/' + n.uuid, token=op)[1]['attrs']['name'], ['fixture-renommee'])
                status, me = n.http('/v1/self', token=session_avant)
                self.assertEqual(status, 200)
                self.assertEqual(me['youare']['attrs']['uuid'], [n.uuid])
                self.assertEqual(n.http('/v1/auth', {'step': {'init2': {'username': ancien, 'issue': 'token', 'privileged': False}}})[0], 404)
                passkey_login('Fixture-Renommee')
                self.assertTrue(m.renommer(api, n.uuid, ancien, 'Fixture-Renommee', op)['deja_renomme'])
                # Retour ciblé effectif, puis renommage à nouveau avec la même passkey.
                m.renommer(api, n.uuid, 'fixture-renommee', ancien, op)
                passkey_login(ancien)
                m.renommer(api, n.uuid, ancien, 'Fixture-Renommee', op)
                passkey_login('Fixture-Renommee')
            finally:
                browser.close()


if __name__ == '__main__':
    unittest.main()
