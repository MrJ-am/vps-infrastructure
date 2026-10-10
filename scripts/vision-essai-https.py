"""Contrôles publics de l'essai : TLS, artefacts exacts et accès falsifiés refusés."""
import hashlib
import importlib.util
import json
from pathlib import Path
import ssl
import sys
import time
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('https_essai',ROOT/'scripts/identite-amorcage-https.py')
h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)


class RefusPublic(ValueError):
    def __init__(self,phase,route,statut,raison):
        self.projection=dict(controle_https_refuse=True,phase=phase,route=route,
            statut=statut,raison=raison)
        super().__init__('Contrôle public refusé')


def demander(opener,origine,route,**options):
    for tentative in range(4):
        r=h.demander(opener,origine,route,**options)
        if r[0]!=429:return r
        if tentative<3:
            try:delai=int(r[1].get('Retry-After','1'))
            except ValueError:delai=1
            time.sleep(max(1,min(delai,5)))
    return r


def verifier(opener,manifeste):
    if len(manifeste['fichiers'])!=22:raise ValueError('Manifeste incomplet')
    origine='https://vision.mrj.am'
    aliases={'index.html':'/','app.html':'/docs','privacy.html':'/privacy'}
    for nom,empreinte in manifeste['fichiers'].items():
        code,_,body=demander(opener,origine,aliases.get(nom,'/'+nom))
        if code!=200:raise RefusPublic('artefact',aliases.get(nom,'/'+nom),code,'statut_inattendu')
        if hashlib.sha256(body).hexdigest()!=empreinte:
            raise RefusPublic('artefact',aliases.get(nom,'/'+nom),code,'empreinte_differente')
    code,_,body=demander(opener,origine,'/interface-manifest.json')
    if code!=200:raise RefusPublic('manifeste','/interface-manifest.json',code,'statut_inattendu')
    if json.loads(body)!=manifeste:raise RefusPublic('manifeste','/interface-manifest.json',code,'contenu_different')
    for entetes in ({},{'X-Mrj-User':'qualification-falsifiee','X-Vision-Administration':'1',
            'X-Mrj-Admin':'1','X-CSRF-Token':'invalide','Cookie':'__Host-mrj_session=invalide; __Secure-mrj_session=invalide'}):
        for route in ('/auth/session','/api/gestion/comptes','/api/v1/health','/mcp'):
            code=demander(opener,origine,route,headers=entetes)[0]
            if code!=401:raise RefusPublic('lecture_privee',route,code,'authentification_attendue')
        for route in ('/api/gestion/comptes','/api/web/effacer_compte'):
            headers=dict(entetes,Origin=origine,**{'Content-Type':'application/json'})
            code=demander(opener,origine,route,headers=headers,data=b'{}')[0]
            if code!=401:raise RefusPublic('mutation_privee',route,code,'authentification_attendue')
    h.verifier(opener,demander_fn=demander)
    return dict(interface_exacte=True,fichiers_interface=22,https=True,
        acces_anonyme_refuse=True,identite_falsifiee_refusee=True,
        mutation_anonyme_refusee=True,compte_utilise=False)


if __name__=='__main__':
    try:
        with zipfile.ZipFile(ROOT/'vendor/vision-multiutilisateur-interface.zip') as z:
            manifeste=json.loads(z.read('manifest.json'))
        context=ssl.create_default_context();context.minimum_version=ssl.TLSVersion.TLSv1_2
        opener=urllib.request.build_opener(urllib.request.HTTPSHandler(context=context),h.SansRedirection())
        print(json.dumps(verifier(opener,manifeste)))
    except RefusPublic as erreur:
        print(json.dumps(erreur.projection),flush=True)
        sys.exit('Contrôles HTTPS refusés ; aucune réponse privée affichée.')
    except Exception as erreur:
        raisons={'Issuer différent':'issuer_different','Endpoint hors issuer':'endpoint_hors_issuer',
            'En-têtes de confidentialité absents':'entetes_absents','Clés publiques absentes ou privées':'cles_refusees',
            'Route réservée publiquement accessible':'route_identite_reservee',
            'Enregistrement dynamique accessible':'enregistrement_dynamique',
            'Offre de sources indisponible':'sources_indisponibles'}
        raison=raisons.get(str(erreur),'refus_non_classe')
        print(json.dumps(dict(controle_https_refuse=True,phase='identite_ou_transport',raison=raison)),flush=True)
        sys.exit('Contrôles HTTPS refusés ; aucune réponse privée affichée.')
