#!/usr/bin/env python3
"""Contrôle HTTPS réel, sans écrire de fiche ni exposer de secret dans les preuves."""
import base64
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.request
from playwright.sync_api import sync_playwright, expect

ORIGINE='https://vision.mrj.am'


def requete(chemin, donnees=None, entetes=None):
    for essai in range(8):
        req=urllib.request.Request(ORIGINE+chemin,None if donnees is None else json.dumps(donnees).encode(),
            {'Content-Type':'application/json','Origin':ORIGINE,**(entetes or {})})
        try:r=urllib.request.urlopen(req,timeout=20)
        except urllib.error.HTTPError as e:r=e
        with r:statut,headers,corps=r.status,r.headers,r.read()
        if statut!=429 or essai==7:return statut,headers,corps
        time.sleep(1)


def rpc(methode, parametres, entetes):
    statut,_,corps=requete('/mcp',{'jsonrpc':'2.0','id':1,'method':methode,'params':parametres},entetes)
    assert statut==200,'MCP doit répondre 200'
    resultat=json.loads(corps)
    assert 'result' in resultat and 'error' not in resultat,'Réponse MCP invalide'
    return resultat['result']


def verifier():
    utilisateur=os.environ['VISION_API_USERNAME'];mot_de_passe=os.environ['VISION_API_PASSWORD']
    basic={'Authorization':'Basic '+base64.b64encode((utilisateur+':'+mot_de_passe).encode()).decode()}
    assert requete('/api/v1/health',entetes=basic)[0]==200,'Basic API indisponible'
    assert 'serverInfo' in rpc('initialize',{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'controle','version':'1'}},basic)
    for entetes in ({},{'Authorization':'Bearer invalide'},{'X-Vision-Authenticated':'1','X-Vision-Browser':'1'}):
        assert requete('/mcp',{},entetes)[0]==401,'MCP non protégé'
    assert requete('/_vision_mcp_token')[0]==404,'Route interne exposée'
    statut,headers,corps=requete('/auth/login',{'username':utilisateur,'password':mot_de_passe})
    assert statut==200,'Connexion impossible'
    session=json.loads(corps);cookie=headers['Set-Cookie'].split(';')[0]
    prives={'Cookie':cookie,'X-CSRF-Token':session['csrf']}
    cree=False
    try:
        statut,_,corps=requete('/auth/mcp-token',entetes=prives)
        assert statut==200 and not json.loads(corps)['active'],'Un token existe déjà : ne pas le remplacer pendant le contrôle'
        assert requete('/auth/mcp-token',{'action':'creer'},{'Cookie':cookie})[0]==403,'CSRF non exigé'
        assert requete('/auth/mcp-token',{'action':'creer'},{**prives,'Origin':'https://autre.mrj.am'})[0]==403,'Origine étrangère acceptée'
        with sync_playwright() as p:
            navigateur=p.chromium.launch()
            contexte=navigateur.new_context(viewport={'width':375,'height':850})
            nom,valeur=cookie.split('=',1)
            contexte.add_cookies([{'name':nom,'value':valeur,'domain':'.mrj.am','path':'/',
                'secure':True,'httpOnly':True,'sameSite':'Lax'}])
            page=contexte.new_page();erreurs=[]
            page.on('pageerror',lambda _:erreurs.append(True))
            page.goto(ORIGINE+'/auth/mcp',wait_until='networkidle')
            expect(page.get_by_role('button',name='Créer le token',exact=True)).to_be_visible()
            for largeur in (375,1280):
                page.set_viewport_size({'width':largeur,'height':850})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'),'Débordement'
            page.get_by_role('button',name='Créer le token',exact=True).click()
            expect(page.locator('#token')).to_be_visible();cree=True
            token=page.locator('#token').input_value()
            assert len(token)==43,'Token incorrect'
            bearer={'Authorization':'Bearer '+token}
            resultat=rpc('initialize',{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'Mistral-compatibilite','version':'1'}},bearer)
            assert resultat['protocolVersion']=='2025-06-18'
            outils=rpc('tools/list',{},bearer)['tools']
            assert {v['name'] for v in outils}=={'search_memory_sheets','list_due_memory_sheets','get_memory_sheet','save_memory_sheet','record_review'}
            resultat=rpc('tools/call',{'name':'search_memory_sheets','arguments':{'query':'__controle_mcp_sans_creation__','limit':1}},bearer)
            assert not resultat.get('isError',False),'Lecture MCP échouée'
            assert requete('/api/v1/health',entetes=bearer)[0]==401,'Token accepté hors MCP'
            assert requete('/api/web/list',{},bearer)[0]==401,'Token utilisé comme session'
            assert requete('/auth/mcp-token',entetes=bearer)[0]==401,'Token utilisé pour sa gestion'
            assert requete('/mcp',{}, {'Cookie':cookie})[0]==401,'Session acceptée comme token MCP'
            assert requete('/mcp',{'jsonrpc':'2.0','method':'notifications/initialized'},bearer)[0]==202
            page.reload(wait_until='networkidle')
            expect(page.locator('#secret')).to_be_hidden()
            assert page.locator('#token').input_value()==''
            assert page.evaluate('localStorage.length + sessionStorage.length')==0
            page.get_by_role('button',name='Révoquer le token',exact=True).click()
            expect(page.get_by_role('button',name='Créer le token',exact=True)).to_be_visible()
            assert requete('/mcp',{},bearer)[0]==401,'Révocation inefficace'
            assert not erreurs,'Erreur JavaScript'
            contexte.close();navigateur.close()
        print('Bearer, Basic, initialize, cinq outils, lecture, notification, CSRF, séparation, rendu et révocation : OK. Aucune écriture métier.')
    finally:
        if cree:
            assert requete('/auth/mcp-token',{'action':'revoquer'},prives)[0]==200,'Nettoyage du token de contrôle échoué'
        assert requete('/auth/logout',{},prives)[0]==200,'Déconnexion de contrôle échouée'
    assert requete('/auth/session',entetes={'Cookie':cookie})[0]==401,'Session non révoquée'


if __name__=='__main__':verifier()
