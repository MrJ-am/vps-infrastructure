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

def preparer(modele,destination):
    root=Path(destination)
    if not root.is_absolute():raise ValueError('Répertoire privé absolu requis')
    root.mkdir(mode=0o700,parents=True,exist_ok=True)
    if root.is_symlink() or root.stat().st_mode & 0o077:raise ValueError('Répertoire non privé')
    realm=json.loads(Path(modele).read_text())
    if realm['registrationAllowed'] is not False:raise ValueError('Le premier import doit garder les inscriptions fermées')
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
    cible=root/'mrjam-realm.json'
    if cible.exists():raise ValueError('Import déjà préparé : utiliser le fichier existant ou préparer un nouveau staging')
    fd=os.open(cible,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:json.dump(realm,f,ensure_ascii=False);f.flush();os.fsync(f.fileno())
    fd=os.open(root,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)
    return {'import_prive_prepare':True,'inscriptions':False,'secret_affiche':False}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--modele',required=True);p.add_argument('--destination',required=True);a=p.parse_args()
    print(json.dumps(preparer(a.modele,a.destination)))
