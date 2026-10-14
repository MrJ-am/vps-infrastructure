"""Régressions HTTP/SQLite/OIDC/MCP, sans double des fonctions applicatives."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
import secrets
import unittest
from urllib.parse import parse_qs, urlencode, urlsplit

from mcp_reconnexion_fixture import Fixture, VISION, CALLBACK


def header(headers, name):
    return next(v for k,v in headers if k.lower()==name.lower())


class ReconnexionHTTP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f = Fixture(os.environ['VISION_TEST_DIST'],sbcl=os.environ.get('SBCL','sbcl'))
        cls.addClassCleanup(cls.f.__exit__,None,None,None)
        cls.f.__enter__()

    @classmethod
    def tearDownClass(cls):
        assert not cls.f.errors, cls.f.errors

    def setUp(self):
        self.f.faults.clear()
        self.f.access.clear();self.f.refresh.clear()
        self.f.parameters.update(alice=True,bob=True)
        self.f.config.write_text(json.dumps(self.f.parameters))
        for table in ('log_oauth_tokens','log_oauth_codes','log_oauth_requests','log_sessions','log_transactions','log_oauth_clients'):
            self.f.sql('DELETE FROM '+table)
        self.client=self.f.register()

    def login(self, account='alice', *, legacy=False):
        status,hs,_=self.f.request('GET','/auth/connexion?retour=%2F')
        self.assertEqual(status,302)
        binding=header(hs,'Set-Cookie').split(';')[0]
        target=header(hs,'Location')
        callback=self.f.native_return(urlsplit(target).query,account)
        if legacy:
            binding='__Host-mrj_oidc='+binding.split('=',1)[1]
        p=urlsplit(callback)
        status,hs,_=self.f.request('GET',p.path+'?'+p.query,cookies=binding)
        self.assertEqual(status,302)
        cookies=[v for k,v in hs if k.lower()=='set-cookie']
        self.assertTrue(any('Max-Age=0' in c for c in cookies))
        return next(c.split(';')[0] for c in cookies if c.startswith('__Host-mrj_session='))

    def authorize(self, cookies, **kwargs):
        url,verifier,state=self.f.authorization(self.client,**kwargs)
        status,hs,_=self.f.request('GET',url.removeprefix(VISION),cookies=cookies)
        self.assertEqual(status,302)
        location=header(hs,'Location')
        self.assertTrue(location.startswith('/#autorisation-mcp='))
        ident=location.split('=',1)[1]
        status,_,d=self.f.request('GET','/auth/oauth-demande?id='+ident,cookies=cookies)
        self.assertEqual(status,200)
        return d,verifier,state

    def consent(self,cookies,request,decision='autoriser',*,csrf=None,origin=VISION):
        if csrf is None:
            status,_,s=self.f.request('GET','/auth/session',cookies=cookies)
            self.assertEqual(status,200);csrf=s['csrf']
        return self.f.request('POST','/auth/oauth-consentement',{'id':request['id'],'decision':decision},
                              cookies=cookies,csrf=csrf,origin=origin)

    def grant(self,cookies):
        request,verifier,state=self.authorize(cookies)
        status,_,d=self.consent(cookies,request)
        self.assertEqual(status,200)
        p=parse_qs(urlsplit(d['redirection']).query)
        self.assertEqual(p['state'],[state])
        status,_,tokens=self.f.exchange(self.client,p['code'][0],verifier)
        self.assertEqual(status,200)
        return tokens

    def assert_mcp(self, token):
        for ident,method in enumerate(('initialize','tools/list')):
            status,_,d=self.f.request('POST','/mcp',dict(jsonrpc='2.0',id=ident,method=method,
                params={'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'fixture','version':'1'}} if ident==0 else {}),bearer=token)
            self.assertEqual(status,200);self.assertNotIn('error',d)
            if method=='tools/list':self.assertIn('tutoriel',[t['name'] for t in d['result']['tools']])

    def test_sans_cookie_entree_oauth_conserve_tous_les_parametres(self):
        url,_,_=self.f.authorization(self.client,state='état + / ? & = % 👩‍🏫')
        status,hs,_=self.f.request('GET',url.removeprefix(VISION))
        self.assertEqual(status,302)
        target=header(hs,'Location')
        self.assertEqual(parse_qs(urlsplit(target).query)['retour'],[url.removeprefix(VISION)])
        status,hs,_=self.f.request('GET',target)
        self.assertEqual(status,302)
        self.assertTrue(header(hs,'Location').startswith('https://log.mrj.am/ui/oauth2?'))

    def test_cookie_inconnu_ou_malforme_reprend_connexion(self):
        url,_,_=self.f.authorization(self.client)
        for cookie in ('__Host-mrj_session=invalide','__Host-mrj_session='+secrets.token_urlsafe(32),
                       '; '.join('__Host-mrj_session='+secrets.token_urlsafe(32) for _ in range(2))):
            with self.subTest(cookie_type='inconnu_ou_malforme'):
                status,hs,_=self.f.request('GET',url.removeprefix(VISION),cookies=cookie)
                self.assertEqual(status,302);self.assertTrue(header(hs,'Location').startswith('/auth/connexion?'))

    def test_cookie_present_mais_refresh_revoque_reprend_et_mcp_fonctionne(self):
        cookies=self.login();old=self.grant(cookies)
        self.f.invalidate_native()
        url,_,_=self.f.authorization(self.client)
        status,hs,_=self.f.request('GET',url.removeprefix(VISION),cookies=cookies)
        self.assertEqual(status,302)
        self.assertTrue(header(hs,'Location').startswith('/auth/connexion?'))
        self.assertEqual(self.f.sql('SELECT count(*) AS n FROM log_sessions')[0]['n'],0)
        self.assertEqual(self.f.request('POST','/mcp',{},bearer=old['access_token'])[0],401)
        self.assert_mcp(self.grant(self.login())['access_token'])

    def test_session_locale_expiree_reprend_connexion(self):
        cookies=self.login()
        self.f.sql('UPDATE log_sessions SET expires=0')
        url,_,_=self.f.authorization(self.client)
        status,hs,_=self.f.request('GET',url.removeprefix(VISION),cookies=cookies)
        self.assertEqual(status,302);self.assertTrue(header(hs,'Location').startswith('/auth/connexion?'))

    def test_access_natif_expire_refresh_valide_transparent(self):
        cookies=self.login()
        before=self.f.sql('SELECT digest,access,refresh FROM log_sessions')[0]
        self.f.invalidate_native(revoked=False)
        self.assert_mcp(self.grant(cookies)['access_token'])
        after=self.f.sql('SELECT digest,access,refresh FROM log_sessions')[0]
        self.assertEqual(before['digest'],after['digest'])
        self.assertNotEqual(before['refresh'],after['refresh'])

    def test_panne_introspection_ne_supprime_pas_session(self):
        cookies=self.login();tokens=self.grant(cookies)
        before=self.f.sql('SELECT * FROM log_sessions')
        self.f.faults['/oauth2/token/introspect']=(503,{'error':'temporarily_unavailable'})
        url,_,_=self.f.authorization(self.client)
        status,headers,error=self.f.request('GET',url.removeprefix(VISION),cookies=cookies)
        self.assertEqual((status,error),(503,{'error':'temporarily_unavailable'}))
        self.assertEqual(header(headers,'Retry-After'),'5')
        status,_,error=self.f.request('POST','/oauth/token',urlencode(dict(grant_type='refresh_token',
            client_id=self.client,refresh_token=tokens['refresh_token'])))
        self.assertEqual((status,error),(503,{'error':'temporarily_unavailable'}))
        self.assertEqual(self.f.sql('SELECT * FROM log_sessions'),before)
        self.f.faults.clear()
        self.assert_mcp(self.grant(cookies)['access_token'])

    def test_panne_renouvellement_ne_supprime_pas_session(self):
        cookies=self.login();self.f.invalidate_native(revoked=False)
        before=self.f.sql('SELECT * FROM log_sessions')
        for status in (400,401,429,500,503):
            with self.subTest(status=status):
                self.f.faults['/oauth2/token']=(status,{'error':'server_error'})
                self.assertEqual(self.f.request('GET','/auth/session',cookies=cookies)[0],503)
                self.assertEqual(self.f.sql('SELECT * FROM log_sessions'),before)
        self.f.faults.clear();self.assert_mcp(self.grant(cookies)['access_token'])

    def test_introspection_incomplete_ne_detruit_pas_session(self):
        cookies=self.login();before=self.f.sql('SELECT * FROM log_sessions')
        for document in ({},{'active':'false'},{'active':None}):
            with self.subTest(document_type='incomplet'):
                self.f.faults['/oauth2/token/introspect']=(200,document)
                self.assertEqual(self.f.request('GET','/auth/session',cookies=cookies)[0],503)
                self.assertEqual(self.f.sql('SELECT * FROM log_sessions'),before)

    def test_scope_omis_et_state_encoded_conserves(self):
        cookies=self.login()
        for state in ('état + / ? & = % 👩‍🏫','a'*1024):
            with self.subTest(longueur=len(state)):
                request,verifier,_=self.authorize(cookies,scope=False,state=state)
                status,_,d=self.consent(cookies,request)
                self.assertEqual(status,200)
                q=parse_qs(urlsplit(d['redirection']).query)
                self.assertEqual(q['state'],[state])
                self.assert_mcp(self.f.exchange(self.client,q['code'][0],verifier)[2]['access_token'])

    def test_deux_connexions_paralleles_et_retour_inverse(self):
        starts=[]
        for _ in range(2):
            status,hs,_=self.f.request('GET','/auth/connexion')
            self.assertEqual(status,302)
            starts.append((header(hs,'Location'),header(hs,'Set-Cookie').split(';')[0]))
        self.assertNotEqual(starts[0][1].split('=',1)[0],starts[1][1].split('=',1)[0])
        cookies='; '.join(cookie for _,cookie in starts)
        for url,_ in reversed(starts):
            callback=self.f.native_return(urlsplit(url).query,'alice')
            status,hs,_=self.f.request('GET',callback.removeprefix(VISION),cookies=cookies)
            self.assertEqual(status,302)
            cleared=next(v for k,v in hs if k.lower()=='set-cookie' and 'Max-Age=0' in v)
            self.assertIn(parse_qs(urlsplit(url).query)['state'][0],cleared)
        self.assertEqual(self.f.sql('SELECT count(*) AS n FROM log_sessions')[0]['n'],2)

    def test_cookie_transaction_historique_reste_valide(self):
        self.assert_mcp(self.grant(self.login(legacy=True))['access_token'])

    def test_callback_sans_cookie_et_rejeu_refuses(self):
        _,hs,_=self.f.request('GET','/auth/connexion')
        url=header(hs,'Location');cookie=header(hs,'Set-Cookie').split(';')[0]
        callback=self.f.native_return(urlsplit(url).query,'alice').removeprefix(VISION)
        self.assertEqual(self.f.request('GET',callback)[0],401)
        self.assertEqual(self.f.sql('SELECT count(*) AS n FROM log_sessions')[0]['n'],0)
        self.assertEqual(self.f.request('GET',callback,cookies=cookie)[0],302)
        self.assertEqual(self.f.request('GET',callback,cookies=cookie)[0],401)
        self.assertEqual(self.f.sql('SELECT count(*) AS n FROM log_sessions')[0]['n'],1)

    def test_expiration_transaction_et_mauvais_binding_refuses(self):
        _,hs,_=self.f.request('GET','/auth/connexion')
        cookie=header(hs,'Set-Cookie').split(';')[0]
        callback=self.f.native_return(urlsplit(header(hs,'Location')).query,'alice').removeprefix(VISION)
        bad=cookie.split('=',1)[0]+'='+secrets.token_urlsafe(32)
        self.assertEqual(self.f.request('GET',callback,cookies=bad)[0],401)
        self.f.sql('UPDATE log_transactions SET expires=0')
        self.assertEqual(self.f.request('GET',callback,cookies=cookie)[0],401)
        self.assertEqual(self.f.sql('SELECT count(*) AS n FROM log_sessions')[0]['n'],0)

    def test_csrf_origine_et_compte_etrangers_refuses_sans_consommation(self):
        alice=self.login();bob=self.login('bob');request,_,_=self.authorize(alice)
        for origin in (None,'null','https://intrus.example.test'):
            with self.subTest(origin=origin):
                self.assertEqual(self.consent(alice,request,origin=origin)[0],403)
        self.assertEqual(self.consent(alice,request,csrf='incorrect')[0],403)
        self.assertEqual(self.consent(bob,request)[0],400)
        self.assertEqual(self.f.request('GET','/auth/oauth-demande?id='+request['id'],cookies=bob)[0],404)
        self.assertEqual(self.consent(alice,request)[0],200)

    def test_refus_consentement_ne_cree_pas_de_grant(self):
        cookies=self.login();request,_,state=self.authorize(cookies)
        status,_,d=self.consent(cookies,request,'refuser')
        self.assertEqual(status,200)
        self.assertEqual(parse_qs(urlsplit(d['redirection']).query),dict(state=[state],error=['access_denied']))
        self.assertEqual(self.f.sql('SELECT count(*) AS n FROM log_oauth_codes')[0]['n'],0)

    def test_demande_expiree_peut_recommencer_sans_changer_pkce(self):
        cookies=self.login();request,verifier,state=self.authorize(cookies)
        self.f.sql('UPDATE log_oauth_requests SET expires=0')
        self.assertEqual(self.consent(cookies,request)[0],400)
        status,hs,_=self.f.request('GET',request['reprise'],cookies=cookies)
        self.assertEqual(status,302)
        ident=header(hs,'Location').split('=',1)[1]
        self.assertNotEqual(ident,request['id'])
        status,_,d=self.consent(cookies,dict(id=ident))
        p=parse_qs(urlsplit(d['redirection']).query)
        self.assertEqual(p['state'],[state])
        self.assertEqual(self.f.exchange(self.client,p['code'][0],verifier)[0],200)

    def test_code_pkce_mauvais_client_et_rejeu_refuses(self):
        cookies=self.login();request,verifier,_=self.authorize(cookies)
        _,_,d=self.consent(cookies,request);code=parse_qs(urlsplit(d['redirection']).query)['code'][0]
        for client,proof in ((self.client,secrets.token_urlsafe(32)),(self.f.register(),verifier)):
            status,_,error=self.f.exchange(client,code,proof)
            self.assertEqual((status,error),(400,{'error':'invalid_grant'}))
        self.assertEqual(self.f.exchange(self.client,code,verifier)[0],200)
        self.assertEqual(self.f.exchange(self.client,code,verifier)[2],{'error':'invalid_grant'})

    def test_code_concurrent_consomme_une_seule_fois(self):
        cookies=self.login();request,verifier,_=self.authorize(cookies)
        _,_,d=self.consent(cookies,request);code=parse_qs(urlsplit(d['redirection']).query)['code'][0]
        with ThreadPoolExecutor(max_workers=6) as pool:
            results=list(pool.map(lambda _:self.f.exchange(self.client,code,verifier)[0],range(6)))
        self.assertEqual(sorted(results),[200,400,400,400,400,400])

    def test_rotation_refresh_et_rejeu_revoquent_famille(self):
        tokens=self.grant(self.login())
        request=urlencode(dict(grant_type='refresh_token',client_id=self.client,refresh_token=tokens['refresh_token']))
        status,_,new=self.f.request('POST','/oauth/token',request)
        self.assertEqual(status,200);self.assert_mcp(new['access_token'])
        self.assertNotEqual(tokens['refresh_token'],new['refresh_token'])
        self.assertEqual(self.f.request('POST','/oauth/token',request)[2],{'error':'invalid_grant'})
        self.assertEqual(self.f.request('POST','/mcp',{},bearer=new['access_token'])[0],401)
        self.assert_mcp(self.grant(self.login())['access_token'])

    def test_refresh_expire_et_revoque_signale_reautorisation(self):
        for mode in ('expire','revoque','session'):
            with self.subTest(mode=mode):
                tokens=self.grant(self.login())
                if mode=='expire':self.f.sql("UPDATE log_oauth_tokens SET expires=0 WHERE kind='refresh'")
                elif mode=='revoque':self.f.request('POST','/oauth/revoke',urlencode(dict(client_id=self.client,token=tokens['refresh_token'])))
                else:self.f.invalidate_native()
                status,_,error=self.f.request('POST','/oauth/token',urlencode(dict(grant_type='refresh_token',client_id=self.client,refresh_token=tokens['refresh_token'])))
                self.assertEqual((status,error),(400,{'error':'invalid_grant'}))

    def test_deconnexion_invalide_mcp_et_nouvelle_connexion_reussit(self):
        cookies=self.login();tokens=self.grant(cookies)
        csrf=self.f.request('GET','/auth/session',cookies=cookies)[2]['csrf']
        self.assertEqual(self.f.request('POST','/auth/logout',{},cookies=cookies,csrf=csrf)[0],200)
        self.assertEqual(self.f.request('POST','/mcp',{},bearer=tokens['access_token'])[0],401)
        self.assert_mcp(self.grant(self.login())['access_token'])

    def test_compte_desactive_ne_reconnecte_pas_silencieusement(self):
        cookies=self.login();tokens=self.grant(cookies)
        self.f.parameters['alice']=False;self.f.config.write_text(json.dumps(self.f.parameters))
        url,_,_=self.f.authorization(self.client)
        self.assertEqual(self.f.request('GET',url.removeprefix(VISION),cookies=cookies)[0],403)
        self.assertNotEqual(self.f.request('POST','/mcp',{},bearer=tokens['access_token'])[0],200)

    def test_parametres_hostiles_ne_redirigent_jamais_au_client(self):
        cookies=self.login();url,_,_=self.f.authorization(self.client)
        q={k:v[0] for k,v in parse_qs(urlsplit(url).query).items()}
        for key,value in (('client_id','inconnu'),('redirect_uri','https://intrus.example.test'),
                          ('resource','https://audition.mrj.am/mcp'),('scope','audition:mcp'),
                          ('code_challenge','invalide'),('code_challenge_method','plain'),
                          ('response_type','token'),('state','x'*1025)):
            with self.subTest(parametre=key):
                status,hs,_=self.f.request('GET','/oauth/authorize?'+urlencode(dict(q,**{key:value})),cookies=cookies)
                self.assertEqual(status,400);self.assertFalse(any(k.lower()=='location' for k,_ in hs))
        for suffix in ('&client_id=duplique','&state=duplique','&scope=vision%ZZmcp','&state=%FF'):
            self.assertEqual(self.f.request('GET',url.removeprefix(VISION)+suffix,cookies=cookies)[0],400)
        self.assertEqual(self.f.sql('SELECT count(*) AS n FROM log_oauth_codes')[0]['n'],0)

    def test_redemarrage_conserve_client_session_demande_et_grant(self):
        cookies=self.login();request,verifier,_=self.authorize(cookies)
        self.f.stop();self.f.start()
        status,_,d=self.consent(cookies,request)
        self.assertEqual(status,200)
        code=parse_qs(urlsplit(d['redirection']).query)['code'][0]
        self.f.stop();self.f.start()
        status,_,tokens=self.f.exchange(self.client,code,verifier)
        self.assertEqual(status,200)
        self.assert_mcp(tokens['access_token'])


if __name__=='__main__':unittest.main(verbosity=2)
