"""Activer la fermeture personnelle native après qualification du service privé.

Maintenance via Actions exclusivement. Aucun rôle de gestion d'identité n'est
accordé à l'administration Vision. Les autres actions natives sont conservées.
"""
import argparse
import json
import os
import subprocess
import urllib.parse
import urllib.request


def configurer(api, realm):
    racine='/admin/realms/'+realm
    action=api(racine+'/authentication/required-actions/delete_account')
    api(racine+'/authentication/required-actions/delete_account',{**action,'enabled':True},'PUT')
    compte=api(racine+'/clients?clientId=account')[0]
    role=api(racine+'/clients/'+compte['id']+'/roles/delete-account')
    defaut=api(racine)['defaultRole']['id']
    composites=api(racine+'/roles-by-id/'+defaut+'/composites')
    if not any(r['id']==role['id'] for r in composites):
        api(racine+'/roles-by-id/'+defaut+'/composites',[role],'POST')
    return {'fermeture_personnelle_activee':True,'role_administrateur_identite_ajoute':False}


def executer(configuration):
    for service in ('mrjam-fermeture','mrjam-admission','vision-cycle'):
        subprocess.run(['systemctl','is-active','--quiet',service],check=True)
    fd=os.open(configuration,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd) as f:
        if os.fstat(f.fileno()).st_mode&0o077:raise ValueError('Configuration privée requise')
        p=json.load(f)
    if set(p)!={'utilisateur','mot_de_passe'}:raise ValueError('Configuration invalide')
    base='http://127.0.0.1:8085'
    class SansRedirection(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*_):return None
    ouvreur=urllib.request.build_opener(urllib.request.ProxyHandler({}),SansRedirection())
    donnees=urllib.parse.urlencode({'client_id':'admin-cli','username':p['utilisateur'],
        'password':p['mot_de_passe'],'grant_type':'password'}).encode()
    with ouvreur.open(urllib.request.Request(base+'/realms/master/protocol/openid-connect/token',donnees),timeout=20) as r:
        jeton=json.load(r)['access_token']
    def api(path,donnees=None,methode=None):
        headers={'Authorization':'Bearer '+jeton};corps=None
        if donnees is not None:corps=json.dumps(donnees).encode();headers['Content-Type']='application/json'
        with ouvreur.open(urllib.request.Request(base+path,corps,headers,method=methode),timeout=20) as r:
            contenu=r.read();return json.loads(contenu) if contenu else None
    return configurer(api,'mrjam')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--configuration-privee',required=True);a=p.parse_args()
    try:print(json.dumps(executer(a.configuration_privee)))
    except Exception:raise SystemExit('Activation de la fermeture interrompue ; aucun détail privé affiché.')
