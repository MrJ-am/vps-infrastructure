#!/usr/bin/env python3
"""Qualifier le realm versionné sur Keycloak jetable (HTTP loopback, H2).

Le conteneur de test doit démarrer avec un administrateur synthétique nommé
qualification / uniquement-test-local. Aucun accès au VPS n'est utilisé.
Prérequis : playwright, cryptography et Chromium. Le realm temporaire est
supprimé à la fin ; aucun jeton ou secret n'est affiché.
"""
import argparse
import base64
import copy
import hashlib
import hmac
import html
import importlib.util
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import socketserver
import ssl
import struct
import tempfile
import time
import threading
import urllib.parse
import urllib.request
import urllib.error

from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives import hashes
from playwright.sync_api import sync_playwright
from smtp_local import Relais
from test_courriel_tls import Dialogue as DialogueTLS

RACINE = Path(__file__).resolve().parents[1]


def decodage(valeur):
    return base64.urlsafe_b64decode(valeur + '=' * (-len(valeur) % 4))


def verifier(port, navigateur):
    assert 38000 <= port < 39000, 'Port loopback de qualification exigé.'
    base = f'http://127.0.0.1:{port}'

    def api(chemin, donnees=None, jeton=None, formulaire=False, methode=None):
        entetes = {}
        corps = None
        if donnees is not None:
            corps = (urllib.parse.urlencode(donnees) if formulaire else json.dumps(donnees)).encode()
            entetes['Content-Type'] = 'application/x-www-form-urlencoded' if formulaire else 'application/json'
        if jeton:
            entetes['Authorization'] = 'Bearer ' + jeton
        with urllib.request.urlopen(urllib.request.Request(base + chemin, corps, entetes, method=methode), timeout=20) as reponse:
            contenu = reponse.read()
            return json.loads(contenu) if contenu else None

    def session_administrative():
        return api('/realms/master/protocol/openid-connect/token',
                   {'client_id': 'admin-cli', 'username': 'qualification', 'password': 'uniquement-test-local',
                    'grant_type': 'password'}, formulaire=True)['access_token']
    admin = session_administrative()
    version = api('/admin/serverinfo', jeton=admin)['systemInfo']['version']
    assert version == '26.7.3', 'Qualifier la version Keycloak épinglée.'
    spec=importlib.util.spec_from_file_location('preparer_identite',RACINE/'scripts/identite-preparer.py')
    preparation=importlib.util.module_from_spec(spec);spec.loader.exec_module(preparation)
    with tempfile.TemporaryDirectory() as root:
        preparation.preparer(RACINE/'operations/identite/realm.json',root)
        modele=json.loads((Path(root)/'mrjam-realm.json').read_text())
        secret_cycle=(Path(root)/'cycle-client.secret').read_text()
        secret_admission=(Path(root)/'admission-client.secret').read_text()
    realm = 'qualification-' + secrets.token_hex(6)
    modele['realm'] = realm
    secret_client = secrets.token_urlsafe(32)
    modele['clients'][0]['secret'] = secret_client
    assert not modele['registrationAllowed']
    relais = Relais('0.0.0.0', 38086).demarrer()
    # Exception limitée au relais synthétique local. L'import de production
    # exige STARTTLS ; sa configuration est testée dans test_courriel.py.
    modele['smtpServer'] = {'host':'127.0.0.1','port':'38086',
                            'from':'qualification@example.test','starttls':'false','ssl':'false','auth':'false'}
    api('/admin/realms', modele, admin)
    try:
        mot_de_passe = secrets.token_urlsafe(32)
        otp = secrets.token_urlsafe(20)
        utilisateur = 'compte-synthetique'
        api('/admin/realms/' + realm + '/users',
            {'username': utilisateur, 'enabled': True, 'emailVerified': True, 'email': 'synthetique@example.test',
             'firstName': 'Compte', 'lastName': 'Synthétique',
             'credentials': [{'type': 'password', 'value': mot_de_passe, 'temporary': False},
                             {'type': 'otp', 'secretData': json.dumps({'value': otp}),
                              'credentialData': json.dumps({'subType': 'totp', 'digits': 6, 'counter': 0,
                                                            'period': 30, 'algorithm': 'HmacSHA1'})}]}, admin)
        profil=api('/admin/realms/'+realm+'/users?username='+utilisateur,jeton=admin)[0]
        jeton_cycle=api('/realms/'+realm+'/protocol/openid-connect/token',
                       {'client_id':'mrjam-cycle','client_secret':secret_cycle,'grant_type':'client_credentials'},formulaire=True)['access_token']
        lu=api('/admin/realms/'+realm+'/users/'+profil['id'],jeton=jeton_cycle)
        assert lu['id']==profil['id'] and lu['email']=='synthetique@example.test'
        try:
            api('/admin/realms/'+realm+'/users/'+profil['id']+'/reset-password',
                {'type':'password','value':'ChangementInterdit123'},jeton_cycle,methode='PUT')
            raise AssertionError('Le processus de préavis ne doit pas pouvoir réinitialiser un mot de passe.')
        except urllib.error.HTTPError as erreur:
            assert erreur.code==403
        jeton_admission=api('/realms/'+realm+'/protocol/openid-connect/token',
            {'client_id':'mrjam-admission','client_secret':secret_admission,'grant_type':'client_credentials'},formulaire=True)['access_token']
        # Le profil ne réclame ni noms légaux ni date de naissance.
        configuration_profil=api('/admin/realms/'+realm+'/users/profile',jeton=admin)
        assert {a['name'] for a in configuration_profil['attributes']}=={'username','email'}
        api('/admin/realms/'+realm+'/users',
            {'username':'nouvelle-admission','email':'nouveau@example.test','emailVerified':True,
             'enabled':False,'requiredActions':['UPDATE_PASSWORD']},jeton_admission)
        admis=api('/admin/realms/'+realm+'/users?username=nouvelle-admission&exact=true',jeton=jeton_admission)[0]
        assert admis['enabled'] is False and admis['emailVerified'] is True
        api('/admin/realms/'+realm+'/users/'+admis['id'],{'enabled':True},jeton_admission,methode='PUT')
        api('/admin/realms/'+realm+'/users/'+admis['id']+'/execute-actions-email?lifespan=600',
            ['UPDATE_PASSWORD'],jeton_admission,methode='PUT')
        creation = relais.messages.get(timeout=15)
        assert str(creation['To'])=='nouveau@example.test'
        # Un relais annonçant AUTH mais pas STARTTLS doit être refusé avant
        # toute transmission d'un credential, même si l'envoi est natif.
        smtp_durci={**modele['smtpServer'],'auth':'true','user':'synthetique@example.test',
                    'password':'credential-synthetique','starttls':'true'}
        api('/admin/realms/'+realm,{'smtpServer':smtp_durci},admin,methode='PUT')
        try:
            api('/admin/realms/'+realm+'/users/'+admis['id']+'/execute-actions-email',
                ['UPDATE_PASSWORD'],jeton_admission,methode='PUT')
            raise AssertionError('Un relais sans STARTTLS a été accepté')
        except urllib.error.HTTPError as erreur:assert erreur.code in (400,500)
        assert relais.auth.empty() and relais.messages.empty()
        # Certificat inconnu, nom erroné et véritable AUTH/DATA après TLS.
        certificats=Path(os.environ['QUALIFICATION_TLS'])
        for certificat,valide in [('autre',False),('nom-invalide',False),('correct',True)]:
            class RelaisTLS(socketserver.ThreadingTCPServer):
                allow_reuse_address=True;daemon_threads=True
            tls=RelaisTLS(('127.0.0.1',38087),DialogueTLS)
            import queue
            tls.auth=queue.Queue();tls.messages=queue.Queue();tls.contexte=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            tls.contexte.load_cert_chain(certificats/(certificat+'.pem'),certificats/(certificat+'.key'))
            threading.Thread(target=tls.serve_forever,daemon=True).start()
            try:
                api('/admin/realms/'+realm,{'smtpServer':{**smtp_durci,'port':'38087'}},admin,methode='PUT')
                try:
                    api('/admin/realms/'+realm+'/users/'+admis['id']+'/execute-actions-email',
                        ['UPDATE_PASSWORD'],jeton_admission,methode='PUT')
                    assert valide,'Une erreur TLS a été ignorée'
                except urllib.error.HTTPError as erreur:
                    assert not valide and erreur.code in (400,500)
                if valide:
                    assert tls.auth.get(timeout=5) is True
                    assert tls.messages.get(timeout=5)
                else:assert tls.auth.empty() and tls.messages.empty()
            finally:tls.shutdown();tls.server_close()
        api('/admin/realms/'+realm,{'smtpServer':modele['smtpServer']},admin,methode='PUT')
        issuer = base + '/realms/' + realm
        protocole = '/realms/' + realm + '/protocol/openid-connect'
        retour = 'https://vision.mrj.am/auth/retour'
        preuve = secrets.token_urlsafe(48)
        nonce = secrets.token_urlsafe(32)
        etat = secrets.token_urlsafe(32)
        parametres = {'client_id': 'mrjam-vision', 'response_type': 'code', 'scope': 'openid',
                      'redirect_uri': retour, 'code_challenge_method': 'S256', 'nonce': nonce,
                      'prompt': 'login', 'max_age': '0', 'state': etat,
                      'code_challenge': base64.urlsafe_b64encode(hashlib.sha256(preuve.encode()).digest()).decode().rstrip('=')}
        with sync_playwright() as p:
            b = p.chromium.launch(**({'executable_path': navigateur} if navigateur else {}))
            try:
                page = b.new_page()
                page.route(retour + '**', lambda route: route.fulfill(status=200, body='Retour de qualification'))
                page.goto(base + protocole + '/auth?' + urllib.parse.urlencode(parametres))
                page.locator('#username').fill(utilisateur)
                page.locator('#password').fill(mot_de_passe)
                page.locator('#kc-login').click()
                page.locator('#otp').wait_for()
                dernier_compteur_otp = int(time.time()) // 30
                compteur = struct.pack('>Q', dernier_compteur_otp)
                empreinte = hmac.new(otp.encode(), compteur, hashlib.sha1).digest()
                position = empreinte[-1] & 15
                code_otp = str((struct.unpack('>I', empreinte[position:position + 4])[0] & 0x7fffffff) % 1000000).zfill(6)
                page.locator('#otp').fill(code_otp)
                page.locator('#kc-login').click()
                page.wait_for_url(retour + '**', timeout=10000)
                reponse = urllib.parse.parse_qs(urllib.parse.urlsplit(page.url).query)
                assert reponse['state'] == [etat]
                code = reponse['code'][0]
                # Reprise native par courriel : l'OTP existant doit survivre.
                page = b.new_page()
                page.route(retour + '**', lambda route: route.fulfill(status=200, body='Retour de qualification'))
                page.goto(base + protocole + '/auth?' + urllib.parse.urlencode(parametres))
                page.locator('a[href*="reset-credentials"]').click()
                page.locator('#username').fill(utilisateur)
                page.locator('[type="submit"]').click()
                message = relais.messages.get(timeout=15)
                texte = message.get_body(preferencelist=('plain',)).get_content()
                liens = [l for l in texte.split() if '/login-actions/action-token?' in l]
                assert len(liens) == 1
                lien = html.unescape(liens[0])
                page.goto(lien)
                page.locator('#password-new').fill(secrets.token_urlsafe(32))
                nouveau = page.locator('#password-new').input_value()
                page.locator('#password-confirm').fill(nouveau)
                page.locator('[type="submit"]').click()
                # force-login termine la récupération sans ouvrir une session.
                page.goto(base + protocole + '/auth?' + urllib.parse.urlencode(parametres))
                page.locator('#username').fill(utilisateur)
                page.locator('#password').fill(nouveau)
                page.locator('#kc-login').click()
                page.locator('#otp').wait_for()
                # Le même lien ne peut pas effectuer une seconde récupération.
                autre = b.new_page(); autre.goto(lien)
                assert autre.locator('#password-new').count() == 0
                autre.close()
                # Le courriel est une autre méthode de connexion, sans pwd AMR.
                page = b.new_page()
                page.route(retour + '**', lambda route: route.fulfill(status=200, body='Retour de qualification'))
                page.goto(base + protocole + '/auth?' + urllib.parse.urlencode(parametres))
                page.locator('#try-another-way').click()
                page.get_by_role('button', name='Recevoir un lien par courriel', exact=False).click()
                page.locator('#mrjam-courriel').fill('synthetique@example.test')
                page.get_by_role('button',name='Recevoir mon lien de connexion',exact=True).click()
                courrier = relais.messages.get(timeout=15)
                texte = courrier.get_body(preferencelist=('plain',)).get_content()
                liens = [l for l in texte.split() if '/login-actions/action-token?' in l]
                assert len(liens) == 1
                lien_magique = html.unescape(liens[0])
                autre = b.new_page(); autre.goto(lien_magique)
                assert autre.locator('#mrjam-confirmer').count() == 0
                assert not autre.url.startswith(retour)
                autre.close()
                page.goto(lien_magique)
                page.locator('#mrjam-confirmer').wait_for()
                assert not page.url.startswith(retour)
                page.locator('#mrjam-confirmer').click()
                page.locator('#otp').wait_for()
                # Le fournisseur refuse le rejeu du code déjà employé lors
                # de la première connexion, même pendant sa fenêtre TOTP.
                while int(time.time()) // 30 == dernier_compteur_otp:
                    time.sleep(0.2)
                compteur = struct.pack('>Q', int(time.time()) // 30)
                empreinte = hmac.new(otp.encode(), compteur, hashlib.sha1).digest(); position = empreinte[-1] & 15
                code_otp = str((struct.unpack('>I', empreinte[position:position + 4])[0] & 0x7fffffff) % 1000000).zfill(6)
                page.locator('#otp').fill(code_otp); page.locator('#kc-login').click()
                page.wait_for_url(retour+'**',timeout=10000)
                magie = urllib.parse.parse_qs(urllib.parse.urlsplit(page.url).query)
                assert magie['state']==[etat]
                jetons_magie = api(protocole+'/token',{'grant_type':'authorization_code','client_id':'mrjam-vision',
                    'client_secret':secret_client,'code':magie['code'][0],'code_verifier':preuve,'redirect_uri':retour},formulaire=True)
                claims_magie=json.loads(decodage(jetons_magie['id_token'].split('.')[1]))
                assert {'email','otp'} <= set(claims_magie.get('amr',[]))
                assert 'pwd' not in claims_magie.get('amr',[])
                assert claims_magie['nonce']==nonce and claims_magie['sub']==profil['id']
                page.goto(lien_magique)
                assert page.locator('#mrjam-confirmer').count()==0
            finally:
                b.close()
        jetons = api(protocole + '/token', {'grant_type': 'authorization_code', 'client_id': 'mrjam-vision',
                     'client_secret': secret_client, 'code': code, 'code_verifier': preuve,
                     'redirect_uri': retour}, formulaire=True)
        entete, contenu, signature = jetons['id_token'].split('.')
        entete_json = json.loads(decodage(entete))
        assert entete_json['alg'] == 'RS256'
        cle = next(c for c in api(protocole + '/certs')['keys'] if c['kid'] == entete_json['kid'])
        publique = rsa.RSAPublicNumbers(int.from_bytes(decodage(cle['e']), 'big'),
                                       int.from_bytes(decodage(cle['n']), 'big')).public_key()
        publique.verify(decodage(signature), (entete + '.' + contenu).encode(), padding.PKCS1v15(), hashes.SHA256())
        affirmations = json.loads(decodage(contenu))
        assert affirmations['iss'] == issuer and affirmations['aud'] == 'mrjam-vision'
        assert affirmations['nonce'] == nonce and affirmations['preferred_username'] == utilisateur
        assert {'pwd', 'otp'} <= set(affirmations.get('amr', []))
        maintenant = int(time.time())
        assert 0 <= maintenant - affirmations['auth_time'] < 60
        assert affirmations['iat'] <= maintenant < affirmations['exp']
        # Le service privé est synthétique ; le fournisseur d'identité est réel.
        # Aucun courriel réel ni effacement de données de production.
        hook = Path(os.environ['QUALIFICATION_HOOK_SECRET']).read_text().strip()
        appels = []; statut = [202]
        class FermetureLocale(BaseHTTPRequestHandler):
            def log_message(self,*_):pass
            def do_POST(self):
                assert self.path=='/fermer'
                assert self.headers['Authorization']=='Bearer '+hook
                donnees=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                assert donnees=={'emetteur':issuer,'sujet':profil['id'],'confirmation':'FERMER MON COMPTE'}
                appels.append(donnees)
                self.send_response(statut[0]);self.send_header('Content-Length','0');self.end_headers()
        fermeture=ThreadingHTTPServer(('127.0.0.1',3028),FermetureLocale)
        threading.Thread(target=fermeture.serve_forever,daemon=True).start()
        try:
            admin = session_administrative()
            action=api('/admin/realms/'+realm+'/authentication/required-actions/delete_account',jeton=admin)
            assert action['enabled'] is False
            spec=importlib.util.spec_from_file_location('configurer_fermeture',RACINE/'scripts/identite-fermeture-configurer.py')
            configuration=importlib.util.module_from_spec(spec);spec.loader.exec_module(configuration)
            actions_avant=api('/admin/realms/'+realm+'/authentication/required-actions',jeton=admin)
            def entretien(path,donnees=None,methode=None):return api(path,donnees,admin,methode=methode)
            for _ in range(2):configuration.configurer(entretien,realm)
            actions_apres=api('/admin/realms/'+realm+'/authentication/required-actions',jeton=admin)
            assert [a for a in actions_avant if a['alias']!='delete_account']==[a for a in actions_apres if a['alias']!='delete_account']
            # Le rôle par défaut donne à tous les comptes leur propre droit de
            # fermeture, sans réattribuer un rôle d'administration d'identité.
            with sync_playwright() as p:
                b=p.chromium.launch(**({'executable_path':navigateur} if navigateur else {}))
                try:
                    page=b.new_page()
                    page.route(retour+'**',lambda route:route.fulfill(status=200,body='Qualification'))
                    page.goto(base+protocole+'/auth?'+urllib.parse.urlencode({**parametres,'kc_action':'delete_account'}))
                    page.locator('#username').fill(utilisateur);page.locator('#password').fill(nouveau)
                    page.locator('#kc-login').click();page.locator('#otp').wait_for()
                    # Attendre un nouveau code après le code du lien magique.
                    precedent=int(time.time())//30
                    while int(time.time())//30==precedent:time.sleep(0.2)
                    compteur=struct.pack('>Q',int(time.time())//30)
                    empreinte=hmac.new(otp.encode(),compteur,hashlib.sha1).digest();position=empreinte[-1]&15
                    valeur=str((struct.unpack('>I',empreinte[position:position+4])[0]&0x7fffffff)%1000000).zfill(6)
                    page.locator('#otp').fill(valeur);page.locator('#kc-login').click()
                    page.locator('#mrjam-fermeture').wait_for()
                    page.locator('#mrjam-fermeture').fill('oui');page.locator('#mrjam-fermer').click()
                    assert not appels
                    page.locator('#mrjam-fermeture').fill('FERMER MON COMPTE');page.locator('#mrjam-fermer').click()
                    page.locator('#mrjam-fermeture').wait_for()
                    assert len(appels)==1
                    admin = session_administrative()
                    assert api('/admin/realms/'+realm+'/users/'+profil['id'],jeton=admin)['enabled']
                    statut[0]=200
                    page.locator('#mrjam-fermeture').fill('FERMER MON COMPTE');page.locator('#mrjam-fermer').click()
                    assert len(appels)==2
                    try:
                        api('/admin/realms/'+realm+'/users/'+profil['id'],jeton=admin)
                        raise AssertionError('Identité native conservée après fermeture réussie')
                    except urllib.error.HTTPError as erreur:assert erreur.code==404
                finally:b.close()
        finally:fermeture.shutdown();fermeture.server_close()
        print(json.dumps({'keycloak': version, 'realm_versionne': True, 'signature_rs256': True,
                          'pkce': True, 'amr_mot_de_passe_otp': True, 'auth_time_recent': True,
                          'recuperation_courriel':True,'otp_conserve':True,'lien_usage_unique':True,
                          'admission_identite_privee':True,'profil_minimal_sans_noms':True,
                          'lien_magique_signe':True,'confirmation_expresse':True,'navigateur_origine_requis':True,
                          'mfa_magique_conserve':True,'amr_courriel_sans_pwd':True,
                          'fermeture_native_privee':True,'mfa_fermeture':True,'confirmation_exacte':True,
                          'echec_service_identite_conservee':True,'identite_supprimee_apres_registre':True,
                          'smtp_natif_starttls_obligatoire_avant_auth':True,
                          'smtp_natif_certificat_et_nom_verifies':True,'smtp_natif_auth_dans_tls':True,
                          'cycle_lecture_identite_sans_reinitialisation':True}))
    finally:
        # Le jeton administrateur de qualification expire pendant les attentes
        # de nouveaux codes OTP. Le nettoyage prend une session neuve.
        admin = session_administrative()
        api('/admin/realms/' + realm, jeton=admin, methode='DELETE')
        relais.shutdown(); relais.server_close()


if __name__ == '__main__':
    arguments = argparse.ArgumentParser(description=__doc__)
    arguments.add_argument('--port', type=int, default=38085)
    arguments.add_argument('--navigateur', default=os.environ.get('CHROMIUM'))
    choix = arguments.parse_args()
    verifier(choix.port, choix.navigateur)
