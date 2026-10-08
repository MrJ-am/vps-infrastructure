"""Préparer le seul import initial privé ; ne crée ni utilisateurs ni rôles.

Exécuter dans le staging root via Actions, puis importer une fois avec Keycloak.
Le secret est généré sur la machine et n'est jamais affiché ou incorporé au store.
"""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import importlib.util

def config_courriel(chemin):
    source=Path(__file__).resolve().parents[1]/'services/mrjam-courriel/courriel.py'
    spec=importlib.util.spec_from_file_location('mrjam_courriel',source)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    config=module.verifier_smtp(module.lire_prive(chemin))
    return {'host':config['host'],'port':str(config['port']),
            'from':config['from_address'],'fromDisplayName':'MrJ.am',
            'auth':'true','user':config['username'],'password':config['password'],
            'starttls':'true','ssl':'false'}

def preparer(modele,destination,smtp=None):
    root=Path(destination)
    if not root.is_absolute():raise ValueError('Répertoire privé absolu requis')
    root.mkdir(mode=0o700,parents=True,exist_ok=True)
    if root.is_symlink() or root.stat().st_mode & 0o077:raise ValueError('Répertoire non privé')
    realm=json.loads(Path(modele).read_text())
    if realm['registrationAllowed'] is not False:raise ValueError('Le premier import doit garder les inscriptions fermées')
    if smtp:realm['smtpServer']=config_courriel(smtp)
    secret=root/'oidc-client.secret'
    # Ne jamais remplacer une clé existante : toute rotation est une opération
    # coordonnée avec l'IdP et mrj-auth, pas un effet de la préparation.
    if not secret.exists():
        fd=os.open(secret,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as f:f.write(secrets.token_urlsafe(32));f.flush();os.fsync(f.fileno())
    if secret.is_symlink() or secret.stat().st_mode & 0o077:raise ValueError('Secret non privé')
    value=secret.read_text().strip()
    if not re.fullmatch(r'[A-Za-z0-9_-]{43}',value):raise ValueError('Format de secret invalide')
    realm['clients'][0]['secret']=value
    cycle=root/'cycle-client.secret'
    if not cycle.exists():
        fd=os.open(cycle,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as f:f.write(secrets.token_urlsafe(32));f.flush();os.fsync(f.fileno())
    if cycle.is_symlink() or cycle.stat().st_mode&0o077:raise ValueError('Secret de cycle non privé')
    cycle_secret=cycle.read_text().strip()
    if not re.fullmatch(r'[A-Za-z0-9_-]{43}',cycle_secret):raise ValueError('Secret de cycle invalide')
    realm['clients'].append({'clientId':'mrjam-cycle','secret':cycle_secret,
        'protocol':'openid-connect','publicClient':False,'serviceAccountsEnabled':True,
        'standardFlowEnabled':False,'directAccessGrantsEnabled':False,'implicitFlowEnabled':False,
        'fullScopeAllowed':False,'redirectUris':[],'webOrigins':[]})
    realm.setdefault('users',[]).append({'username':'service-account-mrjam-cycle','enabled':True,
        'serviceAccountClientId':'mrjam-cycle','clientRoles':{'realm-management':['view-users']}})
    realm.setdefault('clientScopeMappings',{}).setdefault('realm-management',[]).append(
        {'client':'mrjam-cycle','roles':['view-users']})
    cible=root/'mrjam-realm.json'
    if cible.exists():raise ValueError('Import déjà préparé : utiliser le fichier existant ou préparer un nouveau staging')
    fd=os.open(cible,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:json.dump(realm,f,ensure_ascii=False);f.flush();os.fsync(f.fileno())
    fd=os.open(root,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)
    return {'import_prive_prepare':True,'inscriptions':False,'secret_affiche':False,
            'smtp_configure':bool(smtp)}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--modele',required=True);p.add_argument('--destination',required=True);p.add_argument('--smtp-prive');a=p.parse_args()
    print(json.dumps(preparer(a.modele,a.destination,a.smtp_prive)))
