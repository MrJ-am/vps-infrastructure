"""Rejouer le registre durable sur une restauration isolée, avant réouverture.

Aucun contenu n'est écrit ou imprimé. L'effacement confirmé prime après une
panne ayant empêché la réponse HTTP. Ne jamais réattribuer un ancien identifiant.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.parse
import urllib.request
import urllib.error

EMETTEUR='https://log.mrj.am/realms/mrjam'

def charger(registres):
    utilisateurs=set();sujets=set()
    for source in registres:
        for ligne in Path(source).read_text().splitlines():
            p=json.loads(ligne)
            if not isinstance(p,dict):raise ValueError('Registre invalide')
            if set(p)=={'utilisateur','confirmee_a'} or (set(p)=={'version','utilisateur','confirmee_a'} and type(p['version']) is int and p['version']==1):
                ids=[p['utilisateur']]
            elif set(p)=={'version','type','emetteur','sujet','confirmee_a','outils'} and type(p['version']) is int and p['version']==2 and p['type']=='fermeture_commune' and p['emetteur']==EMETTEUR:
                if not isinstance(p['outils'],dict) or set(p['outils'])!={'vision'}:raise ValueError('Outil inconnu')
                ids=p['outils']['vision']
                if not isinstance(ids,list) or len(ids)>10 or not isinstance(p['sujet'],str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}',p['sujet']):raise ValueError('Sujet invalide')
                sujets.add(p['sujet'])
            else:raise ValueError('Registre inconnu')
            if type(p['confirmee_a']) is not int or p['confirmee_a']<=0:raise ValueError('Date invalide')
            for u in ids:
                if not isinstance(u,str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}',u):raise ValueError('Identifiant invalide')
                utilisateurs.add(u)
    return utilisateurs,sujets

def effacer_identites(sujets,configuration):
    # Le serveur de restauration est distinct du port actif 8085 et n'écoute
    # que sur loopback. Le compte de maintenance n'est jamais journalisé.
    fichier=Path(configuration)
    fd=os.open(fichier,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd) as f:
        if os.fstat(f.fileno()).st_mode&0o077:raise ValueError('Configuration privée requise')
        p=json.load(f)
    if set(p)!={'version','base_isolee','realm','utilisateur','mot_de_passe'} or type(p['version']) is not int or p['version']!=1:raise ValueError('Configuration invalide')
    if not re.fullmatch(r'http://127\.0\.0\.1:38\d{3}',p['base_isolee']):raise ValueError('Fournisseur isolé sur loopback requis')
    if not re.fullmatch(r'mrjam|qualification-[a-z0-9-]{1,60}|mrjam-restauration_[a-z0-9_]{1,40}',p['realm']):raise ValueError('Realm isolé invalide')
    base=p['base_isolee'];realm=p['realm']
    def requete(path,donnees=None,jeton=None,methode=None):
        headers={};corps=None
        if donnees is not None:
            corps=urllib.parse.urlencode(donnees).encode();headers['Content-Type']='application/x-www-form-urlencoded'
        if jeton:headers['Authorization']='Bearer '+jeton
        # Aucun proxy ni redirection : la cible privée doit rester loopback.
        class SansRedirection(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*_):return None
        ouvreur=urllib.request.build_opener(urllib.request.ProxyHandler({}),SansRedirection())
        with ouvreur.open(urllib.request.Request(base+path,corps,headers,method=methode),timeout=20) as r:
            contenu=r.read();return json.loads(contenu) if contenu else None
    jeton=requete('/realms/master/protocol/openid-connect/token',{'client_id':'admin-cli',
        'username':p['utilisateur'],'password':p['mot_de_passe'],'grant_type':'password'})['access_token']
    for sujet in sorted(sujets):
        try:requete('/admin/realms/'+realm+'/users/'+sujet,jeton=jeton,methode='DELETE')
        except urllib.error.HTTPError as e:
            if e.code!=404:raise

def rejouer(registre,base,identite=None):
    if not re.fullmatch(r'vision_restauration_[a-z0-9_]{1,40}',base):
        raise ValueError('La cible doit être une restauration isolée vision_restauration_*.')
    registres=[registre] if isinstance(registre,(str,Path)) else registre
    utilisateurs,sujets=charger(registres)
    if sujets:
        if not identite:raise ValueError('Les fermetures communes exigent le fournisseur restauré isolé')
        effacer_identites(sujets,identite)
    # Les valeurs ne peuvent contenir de quote après validation. Ne jamais
    # afficher les identifiants, le registre ou la sortie détaillée de psql.
    sql='BEGIN;\n'
    for sujet in sorted(sujets):
        sql+=f"SELECT vision_gestion.engager_fermeture_identite('{EMETTEUR}','{sujet}','FERMER MON COMPTE'); SELECT vision_gestion.effacer_identite_cycle('{EMETTEUR}','{sujet}','FERMER MON COMPTE');\n"
    for u in sorted(utilisateurs):
        sql+=f"SELECT set_config('vision.utilisateur','{u}',true);\nDO $$ BEGIN IF EXISTS(SELECT FROM vision_gestion.comptes WHERE utilisateur='{u}') THEN PERFORM vision_gestion.effacer('{u}','EFFACER VISION'); END IF; END $$;\n"
    sql+='COMMIT;\n'
    subprocess.run(['psql','-X','--set=ON_ERROR_STOP=1','--dbname='+base],input=sql,text=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
    return len(utilisateurs)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--registre',required=True,action='append');p.add_argument('--base',required=True);p.add_argument('--identite-config');a=p.parse_args()
    try:
        n=rejouer(a.registre,a.base,a.identite_config);print(json.dumps({'registre_rejoue':True,'demandes_distinctes':n,'base_isolee':True}))
    except Exception:raise SystemExit('Rejeu interrompu ; conserver la restauration isolée. Aucun détail privé affiché.')
