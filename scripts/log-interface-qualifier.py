"""Vrai navigateur + API Kanidm réelle + médiation de l'image SBCL partagée.

Toutes les identités, cookies et écritures sont synthétiques et isolés ; aucune
connexion/écriture de production, aucun jeton ou secret dans les rapports.
"""
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
import argparse
import queue
import subprocess
import threading
from email.parser import BytesParser
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from kanidm_reel import KanidmLocal, EchecQualification
from kanidm_politiques import creer_neuf_mfa, code_totp
from log_native_proxy import ProxyLocal


def qualifier(froide=False):
    spec=importlib.util.spec_from_file_location('pont_interface',ROOT/'scripts/mcp-appel.py')
    pont=importlib.util.module_from_spec(spec);spec.loader.exec_module(pont)
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
            proc.stdin.write('(progn '+code+' (format t "PARCOURS-TERMINE~%") (finish-output))\n');proc.stdin.flush()
            if not sorties.get(timeout=45):raise EchecQualification('Assertion froide non terminée')
            return
        r=pont.requete('cl-mcp','tools/call',{'name':'repl-eval','arguments':{'code':code+' (format t "INTERFACE-TERMINE")'}})
        if r.get('isError') or r.get('error_context') or 'INTERFACE-TERMINE' not in r.get('stdout',''):
            raise EchecQualification('Assertion Lisp non terminée : '+str(r.get('error_context',{}).get('condition_type')))
    with KanidmLocal(os.environ['MRJAM_KANIDM'],os.environ['MRJAM_CURL']) as n, sync_playwright() as pw:
        creer_neuf_mfa(n);secret=n.creer_client_oidc()
        p=n.root/'interface.json';result=n.root/'result.json';req=n.root/'requete.json';http=n.root/'http.txt'
        for f in (p,result,req,http):f.touch(mode=0o600)
        params=dict(uuid=n.uuid,secret=secret,curl=str(n.curl),ca=str(n.ca),port=n.port,base=str(n.root/'log.sqlite'),
                    resultat=str(result),http=str(http),mail=n.mail,qualifie_a=int(time.time()),bob_uuid='00000000-0000-4000-8000-000000000001')
        p.write_text(json.dumps(params));path=json.dumps(str(p))
        evaluer('(asdf:load-system "mrjam-metier") '+
                '(asdf:load-asd #P'+json.dumps(str(ROOT/'tests/mrjam-log-parcours-tests.asd'))+') '+
                '(asdf:load-system "mrjam-log-parcours-tests") '+
                '(load '+json.dumps(str(ROOT/'tests/log-presentation.lisp'))+') '+
                '(mrjam-native:initialiser-crypto (uiop:getenv "MRJAM_LIBCRYPTO")) '+
                '(mrjam-native:initialiser-sqlite (uiop:getenv "MRJAM_LIBSQLITE")) '+
                '(uiop:symbol-call :mrjam-log-kanidm-tests :preparer '+path+')')
        appels=[];verrou=threading.Lock()
        def api(body,headers):
            # Le verrou couvre fichier + évaluation + lecture, pas seulement RPC.
            with verrou:
                doc=json.loads(body);appels.append({'action':doc.get('action')})
                req.write_text(json.dumps(dict(headers=headers,corps=body.decode(),sortie=str(http))))
                evaluer('(uiop:symbol-call :mrjam-log-presentation-tests :appeler '+json.dumps(str(req))+')')
                raw=http.read_bytes();head,body=raw.split(b'\r\n\r\n',1);statusline,h=head.split(b'\r\n',1)
                status=int(statusline.split()[1]);appels[-1]['status']=status
                if doc.get('action') in ('auth','reauth') and status==200:
                    state=json.loads(body).get('state',{})
                    if 'success' in state and state['success']!='':raise EchecQualification('Jeton natif transmis au frontend')
                return status,list(BytesParser().parsebytes(h).items()),body
        with ProxyLocal(n,presentation=api,site=ROOT/'interface-log/dist') as proxy:
            browser=pw.chromium.launch(executable_path=os.environ['PLAYWRIGHT_CHROMIUM_EXECUTABLE'],headless=True,
                args=['--host-resolver-rules=MAP log.mrj.am 127.0.0.1, MAP vision.mrj.am 127.0.0.1',
                      '--proxy-server=http://127.0.0.1:9','--proxy-bypass-list=log.mrj.am;vision.mrj.am'])
            try:
                ctx=browser.new_context(ignore_https_errors=True);page=ctx.new_page()
                page.add_init_script('''window.__framesMrJam=0;const initial=requestAnimationFrame;
                    window.requestAnimationFrame=(f)=>initial.call(window,(t)=>{window.__framesMrJam++;f(t)});''')
                errors=[];phase='connexion';page.on('pageerror',lambda e:errors.append(type(e).__name__))
                page.goto(json.loads(result.read_text())['uri'])
                page.get_by_role('textbox',name='Adresse électronique ou identifiant').fill(n.mail)
                page.get_by_role('button',name='Continuer',exact=True).click()
                page.get_by_role('textbox',name='Code de votre authentificateur').fill(str(code_totp(n.mfa_secret)).zfill(6))
                page.get_by_role('button',name='Vérifier',exact=True).click()
                page.get_by_label('Phrase de passe',exact=True).fill(n.password)
                page.get_by_role('button',name='Se connecter',exact=True).click()
                page.get_by_role('button',name='Autoriser',exact=True).click()
                page.wait_for_url('https://vision.mrj.am/auth/retour?*')
                params.update(proxy.captures[-1]);params['cookie']=json.loads(result.read_text())['cookie'];p.write_text(json.dumps(params))
                evaluer('(mrjam-log-parcours-tests:terminer '+path+')')
                avant=len([a for a in appels if a['action']=='auth'])
                evaluer('(mrjam-log-parcours-tests:demarrer '+path+')')
                page.goto(json.loads(result.read_text())['uri']);page.wait_for_url('https://vision.mrj.am/auth/retour?*')
                if len([a for a in appels if a['action']=='auth'])!=avant:raise EchecQualification('Reconnexion inutile')
                page.goto('https://log.mrj.am/ui/profile');page.get_by_role('button',name='Gérer mes authentificateurs').wait_for()
                if page.locator('link[href*="bootstrap"],script[src*="bootstrap"]').count():raise EchecQualification('Interface native encore servie')
                if page.locator('.mrjam').inner_text()!='MrJ.am':raise EchecQualification('Signature non sélectionnable')
                page.get_by_role('button',name='Gérer mes authentificateurs').click()
                phase='verification-recente'
                page.get_by_role('textbox',name='Code de votre authentificateur').fill(str(code_totp(n.mfa_secret)).zfill(6))
                page.get_by_role('button',name='Vérifier',exact=True).click()
                page.get_by_label('Phrase de passe',exact=True).fill(n.password)
                page.get_by_role('button',name='Se connecter',exact=True).click()
                page.get_by_label('Nouvelle phrase de passe').wait_for(timeout=15000)
                phase='force-et-phrase'
                page.get_by_label('Nouvelle phrase de passe').fill('simple')
                page.get_by_text('Force insuffisante selon Kanidm',exact=False).wait_for()
                import secrets
                nouvelle='  雪 '+secrets.token_urlsafe(40)+' e\u0301 phrase 👩‍🏫  '
                page.get_by_label('Nouvelle phrase de passe').fill(nouvelle)
                page.get_by_text('Force suffisante selon Kanidm.',exact=True).wait_for()
                page.get_by_role('button',name='Appliquer cette phrase',exact=True).click()
                page.get_by_role('button',name='Ajouter une passkey',exact=True).wait_for()
                cdp=ctx.new_cdp_session(page);cdp.send('WebAuthn.enable')
                cdp.send('WebAuthn.addVirtualAuthenticator',{'options':{'protocol':'ctap2','transport':'internal',
                    'hasResidentKey':True,'hasUserVerification':True,'isUserVerified':True,'automaticPresenceSimulation':True}})
                page.get_by_label('Nom de l’authentificateur').fill(' Clé 雪 pédagogique ')
                page.get_by_role('button',name='Ajouter une passkey',exact=True).click()
                phase='enrolement-passkey'
                page.get_by_text(' Clé 雪 pédagogique ',exact=True).wait_for()
                page.get_by_role('button',name='Enregistrer',exact=True).click()
                phase='enregistrement'
                page.get_by_role('button',name='Me déconnecter de Log').wait_for()
                page.get_by_role('button',name='Me déconnecter de Log').click()
                page.get_by_role('textbox',name='Adresse électronique ou identifiant').fill(n.mail)
                page.get_by_role('button',name='Continuer',exact=True).click()
                page.get_by_role('button',name='Passkey',exact=True).click()
                phase='connexion-passkey'
                page.get_by_role('button',name='Utiliser ma passkey',exact=True).click()
                page.get_by_role('button',name='Gérer mes authentificateurs').wait_for()
                page.emulate_media(reduced_motion='reduce');page.wait_for_timeout(350)
                avant_frames=page.evaluate('window.__framesMrJam');page.wait_for_timeout(350)
                if page.evaluate('window.__framesMrJam')!=avant_frames:raise EchecQualification('Rafraîchissement persistant au repos')
                page.get_by_role('button',name='Me déconnecter de Log').click()
                page.get_by_role('textbox',name='Adresse électronique ou identifiant').fill(n.mail)
                page.get_by_role('button',name='Continuer',exact=True).click()
                page.get_by_role('button',name='Phrase de passe et TOTP',exact=True).click()
                page.get_by_role('textbox',name='Code de votre authentificateur').fill(str(code_totp(n.mfa_secret)).zfill(6))
                page.get_by_role('button',name='Vérifier',exact=True).click()
                page.get_by_label('Phrase de passe',exact=True).fill(nouvelle)
                page.get_by_role('button',name='Se connecter',exact=True).click()
                page.get_by_role('button',name='Gérer mes authentificateurs').wait_for()
                page.get_by_role('button',name='Voir mes sessions').click()
                page.get_by_role('heading',name='Vos sessions',exact=True).wait_for()
                if page.get_by_role('button',name='Révoquer cette session',exact=True).count()<1:
                    raise EchecQualification('Liste des sessions vide')
                # La récupération est un intent officiel isolé, pas une nouvelle identité.
                op=n.login('idm_admin',n.recuperer('idm_admin'),privilegie=True)
                status,intent=n.http('/v1/person/'+n.uuid+'/_credential/_update_intent/86400',token=op)
                if status!=200:raise EchecQualification('Intent de récupération fixture refusé')
                page.goto('https://log.mrj.am/ui/reset?token='+intent['token'])
                page.get_by_label('Nouvelle phrase de passe').wait_for()
                if '?' in page.url:raise EchecQualification('Intent conservé dans l’adresse')
                page.get_by_role('button',name='Annuler les modifications',exact=True).click()
                page.get_by_role('button',name='Gérer mes authentificateurs').wait_for()
                # APIRequestContext n'hérite pas du host-resolver Chromium.
                # Exercices hostiles directement sur le handler de fixture,
                # sans connexion vers un domaine public ni URI personnelle.
                phase='refus-borne'
                hostile=api(json.dumps({'action':'deconnexion'}).encode(),
                    {'Content-Type':'application/json','Origin':'https://etranger.example.test'})
                if hostile[0]!=403:raise EchecQualification('Origine étrangère acceptée')
                inconnu=api(json.dumps({'action':'/v1/raw/delete'}).encode(),
                    {'Content-Type':'application/json','Origin':'https://log.mrj.am'})
                if inconnu[0]!=400:raise EchecQualification('Chemin arbitraire accepté')
                if errors or proxy.errors:raise EchecQualification('Erreur navigateur/proxy')
                page.screenshot(path=str(ROOT/'state/log-interface-synthese.png'))
                print(json.dumps(dict(connexion_mfa=True,proprietaire='alice-synthetique',reconnexion_sans_auth=True,
                     signature_selectionnable=True,jeton_absent_des_reponses=True,ouverture_securite=True,
                     phrase_unicode_verifiee_par_idp=True,force_native=True,passkey_navigateur_idp_reel=True,
                     recuperation_native=True,sessions_listees=True,origine_etrangere_refusee=True,chemin_arbitraire_refuse=True,image_froide=froide,
                     reduction_mouvement_respectee=True,raf_arrete_au_repos=True,
                     production=False,appels=[a for a in appels if a['status']>=400])))
            except Exception:
                (ROOT/'state/log-interface-diagnostic.json').write_text(json.dumps({'phase':phase,'appels':appels,'erreurs_navigateur':errors,'erreurs_proxy':proxy.errors}))
                # La capture ne contient pas les valeurs de champs de passe.
                raise
            finally:
                browser.close()
                if proc:
                    proc.stdin.close();proc.wait(timeout=10)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--froide',action='store_true');a=p.parse_args()
    try:qualifier(a.froide)
    except Exception as e:
        print('Qualification refusée : '+type(e).__name__+' ; diagnostic de statuts dans state/log-interface-diagnostic.json')
        raise SystemExit(1)
