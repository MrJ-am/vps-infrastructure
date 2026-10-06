#!/usr/bin/env python3
"""Vérifications HTTP et navigateur en lecture seule, sans donnée dans les journaux."""
import base64
import hashlib
import json
import os
from pathlib import Path
import time
import tarfile
import re
import urllib.error
import urllib.request
from playwright.sync_api import sync_playwright, expect

ORIGINE = 'https://' + json.loads(Path('projects.json').read_text())['vision']['domain']


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


def contenu_tutoriel():
    with tarfile.open('vendor/vision-vitrine-source.tar.gz') as archive:
        return json.load(archive.extractfile('docs/tutoriel.json'))


def verifier_decouverte(navigateur):
    """Confronter les pages servies aux chapitres canoniques et aux vrais fichiers."""
    contenu = contenu_tutoriel()
    assert len(contenu['sections']) == 11
    statut, entetes, corps = requete('/mcp-config.json', entetes={'X-Forwarded-Host':'hostile.example'})
    configuration = json.loads(corps)
    assert statut == 200 and configuration == {'url_mcp':ORIGINE+'/mcp','gestion_acces':ORIGINE+'/auth/mcp'}
    assert 'no-store' in entetes.get('Cache-Control','')
    erreurs = []
    dossier = Path('rapports-vision'); dossier.mkdir(exist_ok=True)
    for largeur in (320,375,768,1440):
        contexte = navigateur.new_context(viewport={'width':largeur,'height':900})
        contexte.grant_permissions(['clipboard-read','clipboard-write'])
        page = contexte.new_page()
        page.on('pageerror', lambda _: erreurs.append(True))
        page.goto(ORIGINE, wait_until='networkidle')
        expect(page.get_by_role('heading',name='Apprenez aujourd’hui. Retrouvez-le demain.',exact=True)).to_be_visible()
        expect(page.get_by_role('link',name='Découvrir Vision',exact=True)).to_have_attribute('href','/docs#connexion-mcp')
        assert page.locator('footer').count()==0
        assert 'Une application de' not in page.locator('body').inner_text()
        assert page.locator('img').count()==5
        assert page.locator('img').evaluate_all('(images)=>images.every(i=>i.complete&&i.naturalWidth>0&&i.alt.length>10)')
        assert page.evaluate("async()=> (await document.fonts.load('28px MrJamEcriture')).length>0 && (await document.fonts.load('28px MrJamSignature')).length>0")
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
        page.screenshot(path=str(dossier/f'accueil-{largeur}.png'),full_page=True)
        page.goto(ORIGINE+'/docs',wait_until='networkidle')
        expect(page.get_by_role('combobox',name='Chapitre',exact=True).locator('option')).to_have_count(11)
        page.get_by_role('button',name='Copier l’adresse MCP',exact=True).click()
        expect(page.get_by_text('Adresse copiée.',exact=True)).to_be_visible()
        assert page.evaluate('navigator.clipboard.readText()')==configuration['url_mcp']
        for section in contenu['sections']:
            page.get_by_role('combobox',name='Chapitre',exact=True).select_option(section['id'])
            expect(page.get_by_role('heading',name=section['titre'],exact=True)).to_be_visible()
            expect(page.get_by_text(section['explication'],exact=True)).to_be_visible()
            assert page.url.endswith('#'+section['id'])
            texte=page.locator('body').inner_text()
            assert not re.search(r'PostgreSQL|\bVPS\b|Nginx|CSRF|/api/web',texte,re.I)
            assert '{{url_mcp}}' not in texte
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
        page.goto(ORIGINE+'/docs#connexion-chatgpt',wait_until='networkidle')
        expect(page.get_by_role('combobox',name='Chapitre',exact=True)).to_have_value('connexion-chatgpt')
        page.screenshot(path=str(dossier/f'tutoriel-{largeur}.png'),full_page=True)
        page.goto(ORIGINE+'/privacy',wait_until='networkidle')
        texte=page.locator('body').inner_text()
        assert not re.search(r'PostgreSQL|\bVPS\b|Nginx|CSRF|Erevan|capitales|stabilité|décibels',texte,re.I)
        assert page.locator('footer,img').count()==0
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
        page.screenshot(path=str(dossier/f'confidentialite-{largeur}.png'),full_page=True)
        contexte.close()
    assert not erreurs,'Erreur JavaScript dans les pages publiques'


def verifier():
    manifeste = json.loads(Path(os.environ.get('VISION_INTERFACE_ARTEFACT', 'vendor/vision-interface'), 'manifest.json').read_text())
    statut, _, corps = requete('/interface-manifest.json')
    assert statut == 200 and json.loads(corps) == manifeste, 'Manifeste servi différent'
    routes = {'app.html': '/', 'index.html': '/docs', 'privacy.html': '/privacy'}
    for nom, attendu in manifeste['fichiers'].items():
        statut, _, corps = requete(routes.get(nom, '/' + nom))
        assert statut == 200 and hashlib.sha256(corps).hexdigest() == attendu, 'Fichier servi différent : ' + nom
    assert requete('/api/web/rechercher', {})[0] == 401, 'Accès anonyme non refusé'
    utilisateur, secret = os.environ['VISION_API_USERNAME'], os.environ['VISION_API_PASSWORD']
    basic = base64.b64encode((utilisateur + ':' + secret).encode()).decode()
    statut, _, corps = requete('/api/v1/health', entetes={'Authorization': 'Basic ' + basic})
    assert statut == 200 and json.loads(corps)['version'] == '2.6.1', 'Version serveur différente'
    statut, _, corps = requete('/api/v1/rechercher', {'type':'fiche','requete':'','limite':1}, {'Authorization':'Basic '+basic,'X-Mrj-User':'identite-forgee'})
    assert statut == 200 and json.loads(corps)['total'] > 0, 'Identité Basic ou migration absente'
    fiches = json.loads(corps)['resultats']
    statut, _, corps = requete('/api/v1/lire_politique', {}, {'Authorization':'Basic '+basic})
    assert statut == 200 and 'duree_seance_courte_minutes' in json.loads(corps)['politique']
    if fiches:
        fiche_id = fiches[0]['id']
        statut, _, corps = requete('/api/v1/lien_fiche', {'fiche_id':fiche_id}, {'Authorization':'Basic '+basic})
        lien = json.loads(corps)['url']
        assert statut == 200 and lien == ORIGINE + '/#fiche/' + str(fiche_id)
        statut, _, corps = requete('/api/v1/etat_fiche', {'fiche_id':fiche_id,'limite':1}, {'Authorization':'Basic '+basic})
        rapport = json.loads(corps)
        assert statut == 200 and 'markdown' in rapport and 'total' in rapport and 'suite' in rapport
    statut, _, corps = requete('/api/v1/tutoriel', {'section':'fiches-items'}, {'Authorization':'Basic '+basic})
    assert statut == 200 and json.loads(corps)['section']['id']=='fiches-items'
    with sync_playwright() as p:
        navigateur = p.chromium.launch()
        verifier_decouverte(navigateur)
        contexte = navigateur.new_context(viewport={'width': 1280, 'height': 900})
        page = contexte.new_page()
        erreurs = []
        page.on('pageerror', lambda e: erreurs.append(str(e)))
        page.goto(ORIGINE, wait_until='networkidle')
        expect(page.get_by_role('link', name='Se connecter', exact=True)).to_be_visible()
        page.goto(ORIGINE + '/connexion', wait_until='networkidle')
        expect(page.get_by_label('Identifiant', exact=True)).to_be_visible()
        assert page.evaluate("async () => (await document.fonts.load('28px MrJamSignature')).length > 0"), 'Police absente'
        for largeur in (320, 375, 1280):
            page.set_viewport_size({'width': largeur, 'height': 900})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), 'Débordement'
            # La seule capture publiée est la page de connexion, sans saisie.
            Path('rapports-vision').mkdir(exist_ok=True)
            page.screenshot(path=f'rapports-vision/connexion-{largeur}.png', full_page=True)
        page.get_by_label('Identifiant', exact=True).fill(utilisateur)
        page.get_by_label('Mot de passe', exact=True).fill(secret)
        page.get_by_role('button', name='Se connecter', exact=True).click()
        expect(page.get_by_role('heading', name='Fiches', exact=True)).to_be_visible(timeout=20000)
        page.get_by_label('Ouvrir le menu', exact=True).click()
        expect(page.get_by_role('link', name='Tokens d’accès')).to_have_attribute('href', '/auth/mcp')
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
        lecture = {'type': 'fiche', 'requete': '', 'limite': 1}
        assert requete('/api/web/rechercher', lecture, {'Cookie': entete})[0] == 403, 'CSRF non exigé'
        assert requete('/api/web/rechercher', lecture, {'Cookie': entete, 'X-CSRF-Token': csrf, 'Origin': 'https://autre.mrj.am'})[0] == 403, 'Origine étrangère acceptée'
        assert requete('/api/web/rechercher', lecture, {'Cookie': entete, 'X-CSRF-Token': csrf})[0] == 200
        if fiches:
            page.goto(lien, wait_until='networkidle')
            expect(page.get_by_role('button', name='Réessayer le chargement', exact=True)).to_have_count(0)
            # Aucun contenu personnel ni capture de la fiche n'est publié.
            assert page.url.endswith('/#fiche/' + str(fiche_id))
            # La navigation recharge Elm et referme le menu.
            page.get_by_label('Ouvrir le menu', exact=True).click()
        page.get_by_role('button', name='Se déconnecter', exact=True).click()
        expect(page.get_by_label('Identifiant', exact=True)).to_be_visible()
        assert requete('/auth/session', entetes={'Cookie': entete})[0] == 401, 'Session non révoquée'
        assert not erreurs, 'Erreur JavaScript en production'
        assert page.evaluate('localStorage.length + sessionStorage.length') == 0
        contexte.close()
        navigateur.close()
    print('Artefact exact, cinq visuels, onze chapitres canoniques, MCP public, copie, marque, mobile, confidentialité, connexion, CSRF, Basic et révocation vérifiés ; aucune écriture métier.')


if __name__ == '__main__':
    verifier()

