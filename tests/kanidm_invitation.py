"""Invitation neuve et indication native de force, Chromium/IdP réels isolés."""
import os
from urllib.parse import quote, urlsplit
from playwright.sync_api import sync_playwright
from kanidm_reel import EchecQualification, KanidmLocal


def qualifier(paquet, curl):
    with KanidmLocal(paquet, curl) as n, sync_playwright() as pw:
        op = n.login('idm_admin', n.recuperer('idm_admin'), privilegie=True)
        status, _ = n.http('/v1/person', {'attrs': {
            'name': ['fixture-invite'], 'displayname': ['Élodie 東京 des étoiles'],
            'mail': ['fixture-invite@example.test']}}, token=op)
        if status != 200: raise EchecQualification('création identité neuve refusée')
        status, intent = n.http('/v1/person/fixture-invite/_credential/_update_intent/86400', token=op)
        if status != 200 or not isinstance(intent.get('token'), str):
            raise EchecQualification('invitation native refusée')
        browser = pw.chromium.launch(executable_path=os.environ['PLAYWRIGHT_CHROMIUM_EXECUTABLE'], headless=True)
        try:
            context = browser.new_context(ignore_https_errors=True)
            requests = []; hors_scope = []
            def forward(route):
                url = urlsplit(route.request.url)
                if url.hostname != 'log.mrj.am':
                    hors_scope.append(True); route.abort(); return
                # Seuls chemins/méthodes, jamais query/headers/body/cookies.
                requests.append((route.request.method, url.path))
                response = route.fetch(url=f'https://127.0.0.1:{n.port}'+url.path+('?' + url.query if url.query else ''),
                                       headers={**route.request.all_headers(), 'Host': 'log.mrj.am'})
                route.fulfill(response=response)
            context.route('**/*', forward)
            page = context.new_page()
            page.goto('https://log.mrj.am/ui/reset?token='+quote(intent['token']), wait_until='networkidle')
            page.get_by_role('button', name='Add Password', exact=True).click()
            page.locator('#new-password').wait_for()
            page.locator('#new-password').fill('password')
            page.locator('#new-password').press('End')
            page.wait_for_function('document.querySelector("#password-validation-feedback").textContent.trim().length > 0')
            # La réponse HTMX native insère un div de même id dans sa cible.
            # Cibler le conteneur direct du formulaire, pas un id supposé unique.
            feedback = page.locator('#newPasswordForm > #password-validation-feedback')
            weak = feedback.inner_text()
            if not any(p == '/ui/api/check_password_strength' for _, p in requests):
                raise EchecQualification('absence de vérification native pendant saisie')
            strong = 'Étoile 東京 forêt tranquille ' + n.password + ' et montagne violette'
            if len(strong) > 100: strong = strong[:100]
            page.locator('#new-password').fill(strong)
            page.locator('#new-password').press('End')
            page.wait_for_function('document.querySelector("#password-validation-feedback").textContent.trim().length === 0')
            if page.locator('#new-password').input_value() != strong:
                raise EchecQualification('phrase Unicode/espaces modifiée dans le navigateur')
            if feedback.inner_text().strip():
                raise EchecQualification('phrase forte refusée par jauge native')
            if hors_scope: raise EchecQualification('requête navigateur hors IdP de fixture')
            return {'identite_neuve': True, 'invitation_ui_native': True,
                    'indication_force_pendant_saisie': True, 'unicode_espaces_intacts': True,
                    'aucun_courriel_envoye': True, 'production': False}
        finally:
            browser.close()
