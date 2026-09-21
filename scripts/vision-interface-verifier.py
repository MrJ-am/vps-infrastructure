#!/usr/bin/env python3
"""Vérifications HTTP et navigateur en lecture seule, sans donnée dans les journaux."""
import base64
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.request
from playwright.sync_api import sync_playwright, expect

ORIGINE = 'https://vision.mrj.am'


def requete(chemin, donnees=None, entetes=None):
    for essai in range(6):
        req = urllib.request.Request(ORIGINE + chemin,
            None if donnees is None else json.dumps(donnees).encode(),
            {'Content-Type': 'application/json', 'Origin': ORIGINE, **(entetes or {})})
        try:
            retour = urllib.request.urlopen(req, timeout=20)
        except urllib.error.HTTPError as erreur:
            retour = erreur
        with retour:
            statut, headers, corps = retour.status, retour.headers, retour.read()
        if statut != 429 or essai == 5:
            return statut, headers, corps
        time.sleep(1)


def verifier():
    manifeste = json.loads(Path('vendor/vision-interface/manifest.json').read_text())
    statut, _, corps = requete('/interface-manifest.json')
    assert statut == 200 and json.loads(corps) == manifeste, 'Manifeste servi différent'
    routes = {'app.html': '/', 'index.html': '/docs', 'privacy.html': '/privacy'}
    for nom, attendu in manifeste['fichiers'].items():
        statut, _, corps = requete(routes.get(nom, '/' + nom))
        assert statut == 200 and hashlib.sha256(corps).hexdigest() == attendu, 'Fichier servi différent : ' + nom
    assert requete('/api/web/list', {})[0] == 401, 'Accès anonyme non refusé'
    utilisateur, secret = os.environ['VISION_API_USERNAME'], os.environ['VISION_API_PASSWORD']
    basic = base64.b64encode((utilisateur + ':' + secret).encode()).decode()
    assert requete('/api/v1/health', entetes={'Authorization': 'Basic ' + basic})[0] == 200, 'Accès Basic indisponible'
    with sync_playwright() as p:
        navigateur = p.chromium.launch()
        contexte = navigateur.new_context(viewport={'width': 1280, 'height': 900})
        page = contexte.new_page()
        erreurs = []
        page.on('pageerror', lambda e: erreurs.append(str(e)))
        page.goto(ORIGINE, wait_until='networkidle')
        expect(page.get_by_label('Identifiant', exact=True)).to_be_visible()
        assert page.evaluate("async () => (await document.fonts.load('28px MrJamSignature')).length > 0"), 'Police absente'
        for largeur in (375, 1280):
            page.set_viewport_size({'width': largeur, 'height': 900})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), 'Débordement'
            # La seule capture publiée est la page de connexion, sans saisie.
            Path('rapports-vision').mkdir(exist_ok=True)
            page.screenshot(path=f'rapports-vision/connexion-{largeur}.png', full_page=True)
        page.get_by_label('Identifiant', exact=True).fill(utilisateur)
        page.get_by_label('Mot de passe', exact=True).fill(secret)
        page.get_by_role('button', name='Se connecter', exact=True).click()
        expect(page.get_by_role('heading', name='Mes fiches', exact=True)).to_be_visible(timeout=20000)
        # Attendre la réponse réelle PostgreSQL, même si la collection est vide.
        expect(page.get_by_role('button', name='Réessayer le chargement', exact=True)).to_have_count(0)
        cookies = contexte.cookies(ORIGINE)
        cookie = next(c for c in cookies if c['name'] == '__Secure-mrj_session')
        assert cookie['secure'] and cookie['httpOnly'] and cookie['domain'] in ('.mrj.am', 'mrj.am')
        assert cookie['sameSite'] == 'Lax'
        entete = cookie['name'] + '=' + cookie['value']
        statut, _, donnees = requete('/auth/session', entetes={'Cookie': entete})
        assert statut == 200
        csrf = json.loads(donnees)['csrf']
        lecture = {'query': '__controle_publication_sans_creation__', 'tags': [], 'tagMode': 'all', 'state': 'all', 'sort': 'title', 'direction': 'asc', 'limit': 1, 'offset': 0}
        assert requete('/api/web/list', lecture, {'Cookie': entete})[0] == 403, 'CSRF non exigé'
        assert requete('/api/web/list', lecture, {'Cookie': entete, 'X-CSRF-Token': csrf, 'Origin': 'https://autre.mrj.am'})[0] == 403, 'Origine étrangère acceptée'
        assert requete('/api/web/list', lecture, {'Cookie': entete, 'X-CSRF-Token': csrf})[0] == 200
        page.get_by_role('button', name='Se déconnecter', exact=True).click()
        expect(page.get_by_label('Identifiant', exact=True)).to_be_visible()
        assert requete('/auth/session', entetes={'Cookie': entete})[0] == 401, 'Session non révoquée'
        assert not erreurs, 'Erreur JavaScript en production'
        assert page.evaluate('localStorage.length + sessionStorage.length') == 0
        contexte.close()
        navigateur.close()
    print('Artefact exact, rendu, police, connexion, cookie, CSRF, lecture PostgreSQL, Basic et révocation vérifiés ; aucune écriture métier.')


if __name__ == '__main__':
    verifier()
