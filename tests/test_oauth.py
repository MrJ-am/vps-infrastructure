"""Flux OAuth complet en HTTP local, avec PKCE et jetons indépendants."""
import base64
import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from test_mrj_auth import AuthTests
import unittest


class OAuthTests(AuthTests):
    def envoyer(self, chemin, donnees=None, cookie=None, contenu=None):
        entetes = {'X-Forwarded-Host': 'vision.mrj.am',
                   'X-Forwarded-Proto': 'https'}
        if donnees is not None:
            entetes['Origin'] = 'https://vision.mrj.am'
        if cookie:
            entetes['Cookie'] = cookie
        if contenu is not None:
            entetes['Content-Type'] = contenu
        requete = urllib.request.Request(
            f'http://127.0.0.1:{self.server.server_port}{chemin}',
            donnees, entetes)
        try:
            reponse = urllib.request.urlopen(requete)
        except urllib.error.HTTPError as e:
            reponse = e
        with reponse:
            return reponse.status, reponse.headers, reponse.read().decode()

    def test_decouverte_pkce_consentement_renouvellement(self):
        for chemin in ('/.well-known/oauth-protected-resource/mcp',
                       '/.well-known/oauth-authorization-server'):
            statut, _, corps = self.envoyer(chemin)
            self.assertEqual(statut, 200)
            self.assertIn('vision.mrj.am', corps)
        cookie, session = self.login()
        mistral = self.req('/auth/mcp-token', {'action': 'creer'},
                           {'Cookie': cookie, 'X-CSRF-Token': session['csrf']})[2]['token']
        redirection = 'https://claude.ai/api/mcp/callback'
        donnees = json.dumps({'redirect_uris': [redirection],
                              'client_name': 'Claude', 'token_endpoint_auth_method': 'none'}).encode()
        statut, _, corps = self.envoyer('/oauth/register', donnees,
                                        contenu='application/json')
        self.assertEqual(statut, 201)
        client = json.loads(corps)['client_id']
        preuve = 'a' * 43
        empreinte = base64.urlsafe_b64encode(
            hashlib.sha256(preuve.encode()).digest()).rstrip(b'=').decode()
        parametres = urllib.parse.urlencode({
            'response_type': 'code', 'client_id': client, 'redirect_uri': redirection,
            'code_challenge': empreinte, 'code_challenge_method': 'S256',
            'resource': 'https://vision.mrj.am/mcp', 'state': 'controle'})
        chemin = '/oauth/authorize?' + parametres
        self.assertIn('Connectez-vous', self.envoyer(chemin)[2])
        statut, _, page = self.envoyer(chemin, cookie=cookie)
        self.assertEqual(statut, 200)
        self.assertIn('Autoriser Claude', page)
        self.assertIn('/auth/style.css', page)
        identifiant = re.search(r'name="request_id" value="([^"]+)"', page)[1]
        formulaire = urllib.parse.urlencode(
            {'request_id': identifiant, 'csrf': session['csrf'],
             'decision': 'autoriser'}).encode()
        # urllib suit la redirection ; empêcher l'appel extérieur dans ce test.
        import oauth
        original = oauth.rediriger
        sorties = []
        def capturer(handler, adresse):
            sorties.append(adresse)
            handler.reply(200, {'redirect': adresse})
            return True
        oauth.rediriger = capturer
        try:
            statut, _, _ = self.envoyer('/oauth/authorize', formulaire, cookie,
                                        'application/x-www-form-urlencoded')
        finally:
            oauth.rediriger = original
        self.assertEqual(statut, 200)
        self.assertEqual(len(sorties), 1)
        self.assertTrue(sorties[0].startswith(redirection + '?'))
        code = urllib.parse.parse_qs(urllib.parse.urlsplit(sorties[0]).query)['code'][0]
        echange = urllib.parse.urlencode({
            'grant_type': 'authorization_code', 'client_id': client,
            'code': code, 'redirect_uri': redirection, 'code_verifier': preuve}).encode()
        statut, _, corps = self.envoyer('/oauth/token', echange,
                                        contenu='application/x-www-form-urlencoded')
        self.assertEqual(statut, 200)
        jetons = json.loads(corps)
        bearer = {'Authorization': 'Bearer ' + jetons['access_token']}
        self.assertEqual(self.req('/verify-mcp', headers=bearer)[0], 204)
        self.assertEqual(self.req('/verify-mcp',
                                  headers={'Authorization': 'Bearer ' + mistral})[0], 204)
        self.assertEqual(self.req('/verify', headers=bearer)[0], 401)
        self.assertEqual(self.envoyer('/oauth/token', echange,
                                      contenu='application/x-www-form-urlencoded')[0], 400)
        nouveau = urllib.parse.urlencode({
            'grant_type': 'refresh_token', 'client_id': client,
            'refresh_token': jetons['refresh_token']}).encode()
        self.assertEqual(self.envoyer('/oauth/token', nouveau,
                                      contenu='application/x-www-form-urlencoded')[0], 200)
        self.assertEqual(self.envoyer('/oauth/token', nouveau,
                                      contenu='application/x-www-form-urlencoded')[0], 400)
        connexions = self.req('/auth/oauth-connections', headers={'Cookie': cookie})[2]
        self.assertEqual([c['name'] for c in connexions['connections']], ['Claude'])
        self.assertEqual(self.req('/auth/oauth-connections', {'client_id': client},
                                  {'Cookie': cookie})[0], 403)
        self.assertEqual(self.req('/auth/oauth-connections', {'client_id': client},
                                  {'Cookie': cookie, 'X-CSRF-Token': session['csrf']})[0], 200)
        self.assertEqual(self.req('/verify-mcp', headers=bearer)[0], 401)
        self.assertEqual(self.req('/verify-mcp',
                                  headers={'Authorization': 'Bearer ' + mistral})[0], 204)

    def test_redirections_invalides_et_csrf(self):
        for adresse in ('http://evil.example/callback', 'https://evil.example/callback#fragment'):
            donnees = json.dumps({'redirect_uris': [adresse]}).encode()
            self.assertEqual(self.envoyer('/oauth/register', donnees,
                                           contenu='application/json')[0], 400)
        self.assertEqual(self.envoyer('/oauth/authorize',
                                      b'request_id=x&decision=autoriser&csrf=x',
                                      contenu='application/x-www-form-urlencoded')[0], 403)


if __name__ == '__main__':
    unittest.main()
