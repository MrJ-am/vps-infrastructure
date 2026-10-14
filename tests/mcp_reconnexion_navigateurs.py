"""Parcours du consentement Elm livré avec cookies, redirections et MCP réels.

Le fournisseur OIDC et le callback ChatGPT sont isolés dans la fixture TLS.
Les navigateurs sont obligatoires et explicitement sélectionnés, sans fallback.
"""
import json
import os
import unittest
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import expect, sync_playwright
from mcp_reconnexion_fixture import Fixture, VISION, LOG, CALLBACK


class ReconnexionNavigateur(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine=os.environ['MRJAM_NAVIGATEUR']
        cls.f=Fixture(os.environ['VISION_TEST_DIST'],sbcl=os.environ.get('SBCL','sbcl'))
        cls.addClassCleanup(cls.f.__exit__,None,None,None)
        cls.f.__enter__()
        cls.pw=sync_playwright().start()
        cls.addClassCleanup(cls.pw.stop)
        options={'headless':True,'proxy':{'server':cls.f.proxy_url}}
        if cls.engine=='chromium':options['executable_path']=os.environ['CHROMIUM']
        elif cls.engine=='webkit' and os.environ.get('WEBKIT_EXECUTABLE'):
            options['executable_path']=os.environ['WEBKIT_EXECUTABLE']
        cls.browser=getattr(cls.pw,cls.engine).launch(**options)
        cls.addClassCleanup(cls.browser.close)
        print(cls.engine+' '+cls.browser.version,flush=True)

    @classmethod
    def tearDownClass(cls):
        assert not cls.f.errors, cls.f.errors

    def setUp(self):
        self.f.faults.clear();self.f.drop_consent=False
        self.f.access.clear();self.f.refresh.clear()
        for table in ('log_oauth_tokens','log_oauth_codes','log_oauth_requests','log_sessions','log_transactions','log_oauth_clients'):
            self.f.sql('DELETE FROM '+table)
        self.client=self.f.register()
        self.contexts=[];self.js_errors=[]
        self.context=self.context_new()
        self.page=self.context.new_page()

    def tearDown(self):
        for context in self.contexts:context.close()
        self.assertEqual(self.js_errors,[])

    def context_new(self, width=390):
        options=dict(ignore_https_errors=True,viewport={'width':width,'height':844},locale='fr-FR',
                     reduced_motion='reduce',service_workers='block')
        if self.engine!='firefox':options.update(is_mobile=width<500,has_touch=width<500)
        context=self.browser.new_context(**options)
        context.on('page',lambda page:page.on('pageerror',lambda e:self.js_errors.append(type(e).__name__)))
        context.set_default_timeout(10000)
        self.contexts.append(context)
        return context

    def ready(self,page,account='alice'):
        if urlsplit(page.url).hostname=='log.mrj.am':
            page.get_by_role('button',name='Connexion '+account.title()+' de test',exact=True).click()
        expect(page.get_by_role('button',name='Autoriser',exact=True)).to_be_visible()
        expect(page.get_by_text('Client : ChatGPT de test',exact=True)).to_be_visible()
        self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= innerWidth+1'))

    def open(self,page=None,**kwargs):
        page=page or self.page
        url,verifier,state=self.f.authorization(self.client,**kwargs)
        page.goto(url,wait_until='domcontentloaded')
        self.ready(page)
        return verifier,state

    def approve(self,verifier,state,page=None,*,key=False):
        page=page or self.page
        button=page.get_by_role('button',name='Autoriser',exact=True)
        if key:button.focus();button.press('Enter')
        else:button.click()
        page.wait_for_url(CALLBACK+'?**')
        q=parse_qs(urlsplit(page.url).query)
        self.assertEqual(q['state'],[state]);self.assertNotIn('error',q)
        status,_,tokens=self.f.exchange(self.client,q['code'][0],verifier)
        self.assertEqual(status,200)
        status,_,d=self.f.request('POST','/mcp',{'jsonrpc':'2.0','id':1,'method':'tools/list','params':{}},bearer=tokens['access_token'])
        self.assertEqual(status,200)
        self.assertIn('tutoriel',[t['name'] for t in d['result']['tools']])
        return tokens

    def test_navigation_privee_mobile_et_bureau_jusqua_mcp(self):
        for width in (390,1440):
            with self.subTest(largeur=width):
                context=self.context_new(width)
                page=context.new_page()
                proof,state=self.open(page,state='état + / & = % 👩‍🏫')
                self.approve(proof,state,page,key=True)
                cookies=context.cookies(VISION)
                session=next(c for c in cookies if c['name']=='__Host-mrj_session')
                self.assertTrue(session['secure'] and session['httpOnly'])
                self.assertEqual(session['sameSite'],'Lax')
                self.assertEqual(session['domain'],'vision.mrj.am')
                self.assertFalse(any(c['name'].startswith('__Host-mrj_oidc') for c in cookies))

    def test_session_vision_ouverte_ne_redemande_pas_login(self):
        self.approve(*self.open())
        self.context.clear_cookies(domain='log.mrj.am')
        before=(self.f.calls['/ui/oauth2'],self.f.calls['/fixture-login'])
        proof,state=self.open()
        self.assertEqual((self.f.calls['/ui/oauth2'],self.f.calls['/fixture-login']),before)
        self.approve(proof,state)

    def test_session_log_seule_sso_sans_formulaire(self):
        self.approve(*self.open())
        self.context.clear_cookies(domain='vision.mrj.am')
        before=self.f.calls['/fixture-login']
        proof,state=self.open()
        self.assertEqual(self.f.calls['/fixture-login'],before)
        self.approve(proof,state)

    def test_cookie_vision_survit_au_refresh_natif_revoque(self):
        old=self.approve(*self.open())
        self.f.invalidate_native()
        self.context.clear_cookies(domain='log.mrj.am')
        url,proof,state=self.f.authorization(self.client)
        response=self.page.goto(url,wait_until='domcontentloaded')
        self.assertEqual(response.status,200)
        self.assertEqual(urlsplit(self.page.url).hostname,'log.mrj.am')
        self.ready(self.page);self.approve(proof,state)
        self.assertEqual(self.f.request('POST','/mcp',{},bearer=old['access_token'])[0],401)

    def test_cookie_session_locale_expiree_et_sso(self):
        self.approve(*self.open())
        self.f.sql('UPDATE log_sessions SET expires=0')
        self.approve(*self.open())

    def test_deux_onglets_ouverts_avant_login_retours_inverses(self):
        other=self.context.new_page()
        starts=[]
        for page in (self.page,other):
            url,proof,state=self.f.authorization(self.client)
            page.goto(url)
            expect(page.get_by_role('button',name='Connexion Alice de test')).to_be_visible()
            starts.append((page,proof,state))
        cookies=self.context.cookies(VISION)
        self.assertEqual(len([c for c in cookies if c['name'].startswith('__Host-mrj_oidc_')]),2)
        for page,proof,state in reversed(starts):
            self.ready(page)
            self.approve(proof,state,page)

    def test_autorisation_sans_scope_explicite(self):
        self.approve(*self.open(scope=False))

    def test_recharger_et_retour_arriere_ne_valident_pas_consentement(self):
        proof,state=self.open()
        initial=self.page.url
        self.page.reload();self.ready(self.page)
        self.assertEqual(self.f.sql('SELECT count(*) AS n FROM log_oauth_codes')[0]['n'],0)
        self.approve(proof,state)
        self.page.goto(initial)
        expect(self.page.get_by_text('Cette demande d’autorisation a expiré ou a déjà été utilisée.',exact=False)).to_be_visible()
        expect(self.page.get_by_text('Opération refusée : invalid_request',exact=False)).not_to_be_visible()
        expect(self.page.get_by_role('button',name='Autoriser',exact=True)).not_to_be_visible()
        self.assertEqual(self.f.sql('SELECT count(*) AS n FROM log_oauth_codes')[0]['n'],0)
        self.approve(*self.open())

    def test_refuser_au_clavier_restitue_etat_sans_jeton(self):
        _,state=self.open()
        button=self.page.get_by_role('button',name='Refuser',exact=True)
        button.focus();button.press('Enter')
        self.page.wait_for_url(CALLBACK+'?**')
        self.assertEqual(parse_qs(urlsplit(self.page.url).query),dict(state=[state],error=['access_denied']))
        self.assertEqual(self.f.sql('SELECT count(*) AS n FROM log_oauth_tokens')[0]['n'],0)

    def test_consentement_expire_propose_reprise_complete(self):
        proof,state=self.open()
        self.f.sql('UPDATE log_oauth_requests SET expires=0')
        self.page.get_by_role('button',name='Autoriser',exact=True).click()
        link=self.page.get_by_role('link',name='Recommencer la connexion',exact=True)
        expect(link).to_be_visible();link.click()
        self.ready(self.page);self.approve(proof,state)

    def test_session_expiree_pendant_consentement_reconnexion(self):
        proof,state=self.open()
        self.f.invalidate_native()
        self.page.get_by_role('button',name='Autoriser',exact=True).click()
        expect(self.page.get_by_text('Votre session a expiré.',exact=False)).to_be_visible()
        expect(self.page.get_by_role('button',name='Autoriser',exact=True)).not_to_be_visible()
        self.page.get_by_role('link',name='Recommencer la connexion',exact=True).click()
        self.ready(self.page);self.approve(proof,state)

    def test_panne_fournisseur_pendant_consentement_puis_reprise(self):
        proof,state=self.open()
        before=self.f.sql('SELECT digest,access,refresh FROM log_sessions')
        self.f.faults['/oauth2/token/introspect']=(503,{'error':'temporarily_unavailable'})
        self.page.get_by_role('button',name='Autoriser',exact=True).click()
        expect(self.page.get_by_text('La connexion est temporairement indisponible. Réessayez dans un instant.',exact=True)).to_be_visible()
        expect(self.page.get_by_text('Enregistrement de votre décision…',exact=True)).not_to_be_visible()
        self.assertEqual(self.f.sql('SELECT digest,access,refresh FROM log_sessions'),before)
        self.f.faults.clear()
        self.approve(proof,state)

    def test_reponse_consentement_perdue_apres_ecriture_reprise(self):
        proof,state=self.open()
        before=self.f.calls['/auth/oauth-consentement']
        self.f.drop_consent=True
        self.page.get_by_role('button',name='Autoriser',exact=True).click()
        expect(self.page.get_by_role('link',name='Recommencer la connexion',exact=True)).to_be_visible()
        self.assertEqual(self.f.calls['/auth/oauth-consentement']-before,1)
        self.assertEqual(self.f.sql('SELECT count(*) AS n FROM log_oauth_codes')[0]['n'],1)
        expect(self.page.get_by_text('Enregistrement de votre décision…',exact=True)).not_to_be_visible()
        self.page.get_by_role('link',name='Recommencer la connexion',exact=True).click()
        self.ready(self.page);self.approve(proof,state)

    def test_reponse_avant_envoi_perdue_ne_bloque_pas_bouton(self):
        proof,state=self.open()
        self.context.route(VISION+'/auth/oauth-consentement',lambda route:route.abort(),times=1)
        self.page.get_by_role('button',name='Autoriser',exact=True).click()
        expect(self.page.get_by_role('link',name='Recommencer la connexion',exact=True)).to_be_visible()
        self.assertEqual(self.f.sql('SELECT count(*) AS n FROM log_oauth_codes')[0]['n'],0)
        self.approve(proof,state)

    def test_double_clic_ne_consomme_qu_une_demande(self):
        proof,state=self.open()
        before=self.f.calls['/auth/oauth-consentement']
        self.page.get_by_role('button',name='Autoriser',exact=True).evaluate('(button)=>{button.click();button.click()}')
        self.page.wait_for_url(CALLBACK+'?**')
        self.assertEqual(self.f.calls['/auth/oauth-consentement']-before,1)
        q=parse_qs(urlsplit(self.page.url).query)
        self.assertEqual(q['state'],[state])
        self.assertEqual(self.f.exchange(self.client,q['code'][0],proof)[0],200)

    def test_cookies_effaces_au_retour_refus_sans_autorisation_implicite(self):
        url,_,_=self.f.authorization(self.client)
        self.page.goto(url)
        self.context.clear_cookies(domain='vision.mrj.am')
        self.page.get_by_role('button',name='Connexion Alice de test').click()
        self.page.wait_for_url(VISION+'/auth/retour?**')
        self.assertEqual(self.f.sql('SELECT count(*) AS n FROM log_sessions')[0]['n'],0)
        self.assertEqual(self.f.sql('SELECT count(*) AS n FROM log_oauth_tokens')[0]['n'],0)
        # Nouvelle demande explicite depuis le client : une connexion complète réussit.
        self.approve(*self.open())


if __name__=='__main__':unittest.main(verbosity=2)
