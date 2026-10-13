"""Reconnexion Native par vrai navigateur, même image applicative, données isolées."""
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
import argparse
import subprocess
import threading
import queue
from urllib.parse import parse_qs, urlsplit
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from kanidm_reel import KanidmLocal, EchecQualification
from kanidm_politiques import creer_neuf_mfa, code_totp
from log_native_proxy import ProxyLocal


def verifier(froide=False):
    def module(nom,path):
        s=importlib.util.spec_from_file_location(nom,ROOT/path)
        m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
    pont=module('pont_parcours','scripts/mcp-appel.py');migration=module('clients_parcours','scripts/log-clients-mcp.py')
    proc=None;sorties=queue.Queue()
    if froide:
        proc=subprocess.Popen(['sbcl','--script','tests/log-parcours-froid.lisp'],cwd=ROOT,
             stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
        def lire():
            for ligne in proc.stdout:
                if 'PARCOURS-TERMINE' in ligne:sorties.put(True)
                if 'PARCOURS-ECHEC' in ligne:sorties.put(False)
            sorties.put(False)
        threading.Thread(target=lire,daemon=True).start()
    def evaluer(code):
        if proc:
            proc.stdin.write('(progn '+code+' (format t "~&PARCOURS-TERMINE~%") (finish-output))\n');proc.stdin.flush()
            if not sorties.get(timeout=45):raise EchecQualification('Assertion froide non terminée')
            return
        r=pont.requete('cl-mcp','tools/call',{'name':'repl-eval','arguments':{'code':code+' (format t "PARCOURS-TERMINE")'}})
        if r.get('isError') or r.get('error_context') or 'PARCOURS-TERMINE' not in r.get('stdout',''):
            fd=os.open(ROOT/'state/log-parcours-diagnostic-prive.json',os.O_CREAT|os.O_WRONLY|os.O_TRUNC,0o600)
            # Le diagnostic MCP peut capturer les arguments de fixture dans
            # les locaux. Ne pas conserver ces secrets, même synthétiques.
            with os.fdopen(fd,'w') as f:json.dump({'condition_type':r.get('error_context',{}).get('condition_type'),
                                                 'assertion_terminee':False},f)
            raise EchecQualification('Assertion parcours Lisp non terminée, aucune qualification')
    with KanidmLocal(os.environ['MRJAM_KANIDM'],os.environ['MRJAM_CURL']) as n, sync_playwright() as pw:
        avant=int(time.time());creer_neuf_mfa(n);secret=n.creer_client_oidc()
        fixture=n.root/'parcours.json';result=n.root/'result.json'
        fixture.touch(mode=0o600);result.touch(mode=0o600)
        params=dict(uuid=n.uuid,secret=secret,curl=str(n.curl),ca=str(n.ca),port=n.port,
             base=str(n.root/'log.sqlite'),resultat=str(result),http=str(n.root/'http.txt'),mail=n.mail,
             qualifie_a=avant,bob_uuid='00000000-0000-4000-8000-000000000001')
        fixture.write_text(json.dumps(params));path=json.dumps(str(fixture))
        evaluer('(asdf:load-asd #P'+json.dumps(str(ROOT/'tests/mrjam-log-parcours-tests.asd'))+') '+
                '(asdf:load-system "mrjam-log-parcours-tests") '+
                '(mrjam-native:initialiser-crypto (uiop:getenv "MRJAM_LIBCRYPTO")) '+
                '(mrjam-native:initialiser-sqlite (uiop:getenv "MRJAM_LIBSQLITE")) '+
                '(uiop:symbol-call :mrjam-log-kanidm-tests :preparer '+path+')')
        proxy=ProxyLocal(n);proxy.__enter__()
        browser=pw.chromium.launch(executable_path=os.environ['PLAYWRIGHT_CHROMIUM_EXECUTABLE'],headless=True,
             args=['--host-resolver-rules=MAP log.mrj.am 127.0.0.1, MAP vision.mrj.am 127.0.0.1',
                   '--proxy-server=http://127.0.0.1:9','--proxy-bypass-list=log.mrj.am;vision.mrj.am'])
        try:
            context=browser.new_context(ignore_https_errors=True);captures=proxy.captures;post_log=proxy.posts
            page=context.new_page()
            for tour in (1,2):
                if tour==2:evaluer('(mrjam-log-parcours-tests:demarrer '+path+')')
                d=json.loads(result.read_text());params['cookie']=d['cookie'];nombre=len(post_log)
                page.goto(d['uri'],wait_until='domcontentloaded')
                if tour==1:
                    page.locator('input[name=username]').fill(n.nom);page.locator('form#login').evaluate('(f)=>f.requestSubmit()')
                    page.locator('input[name=totp]').wait_for();page.locator('input[name=totp]').fill(str(code_totp(n.mfa_secret)))
                    page.locator('input[name=password]').evaluate('(input,value)=>{input.value=value}',n.password)
                    page.locator('form#login').evaluate('(f)=>f.requestSubmit()')
                    page.wait_for_function('''location.hostname === "vision.mrj.am" || !!document.querySelector('input[name=consent_token]') || !!document.querySelector('form[action="/ui/login/pw"]')''')
                    if page.locator('form[action="/ui/login/pw"]').count():
                        page.locator('input[name=password]').fill(n.password)
                        page.locator('form#login').evaluate('(f)=>f.requestSubmit()')
                        page.wait_for_function('location.hostname === "vision.mrj.am" || !!document.querySelector("input[name=consent_token]")')
                    if page.locator('input[name=consent_token]').count():
                        page.locator('input[name=consent_token]').evaluate('(i)=>i.closest("form").requestSubmit()')
                page.wait_for_url('https://vision.mrj.am/auth/retour?*',timeout=15000)
                if tour==2 and len(post_log)!=nombre:raise EchecQualification('Reconnexion a relancé le login/consentement natif')
                params.update(captures[-1]);fixture.write_text(json.dumps(params))
                evaluer('(mrjam-log-parcours-tests:terminer '+path+')')
            # Une page native déjà connectée doit rester accessible.
            for chemin in ['/ui/login','/ui/apps','/ui/profile']:
                response=page.goto('https://log.mrj.am'+chemin,wait_until='domcontentloaded')
                attendu='/ui/apps' if chemin=='/ui/login' else chemin
                if response.status!=200 or urlsplit(page.url).path!=attendu:
                    raise EchecQualification('Page native connectée refusée : '+chemin)
            old=n.root/'old.sqlite'
            reference=module('oauth_fixture','services/mrj-auth/oauth.py')
            from types import SimpleNamespace
            reference.initialiser(SimpleNamespace(connect=lambda:sqlite3.connect(old)))
            with sqlite3.connect(old) as db:
                db.execute('INSERT INTO oauth_clients VALUES(?,?,?,?)',('A'*32,'ChatGPT fixture',json.dumps(['https://client.example.test/callback']),100))
            migration.reprendre(migration.lire_clients(old),Path(params['base']))
            evaluer('(mrjam-log-parcours-tests:mcp)')
            if proxy.errors:raise EchecQualification('Erreur inattendue du proxy local')
            print(json.dumps({'connexion_initiale_mfa':True,'reconnexion_cookie_native_sans_login':True,
                'pages_log_connectees':True,'session_vision_precedente_conservee':True,
                'client_historique_nouveau_consentement_pkce':True,'client_inconnu_refuse':True,'production':False}))
        except Exception:
            # Diagnostic de structure seulement : aucune valeur de formulaire,
            # URL complète, cookie, token, copie HTML ou capture d'écran.
            print(json.dumps({'echec_fixture':True,'path':urlsplit(page.url).path,
                'title':page.title(),'inputs':page.locator('input').evaluate_all('(xs)=>xs.map(x=>({name:x.name,type:x.type}))'),
                'cookie_names':[c['name'] for c in context.cookies()], 'post_paths':post_log}),file=sys.stderr)
            raise
        finally:
            browser.close()
            proxy.__exit__()
            if proc:
                proc.stdin.close();proc.wait(timeout=15)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--froide',action='store_true')
    verifier(p.parse_args().froide)
