"""Copie mensuelle sur disque Linux : fichiers chiffrés et empreintes vérifiées.

Ne manipule aucune base en clair. La vérification age prouve le déchiffrement,
pas une restauration PostgreSQL complète ni l'actualité du registre Proton.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


def empreinte(fichier):
    h=hashlib.sha256()
    with fichier.open('rb') as flux:
        for bloc in iter(lambda:flux.read(1024*1024),b''):h.update(bloc)
    return h.hexdigest()


def manifeste(repertoire,date):
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{6}Z',date):raise ValueError('Date de génération invalide')
    root=Path(repertoire)
    fichiers={p.name:empreinte(p) for p in root.glob('*-'+date+'.age') if p.is_file() and not p.is_symlink()}
    if not all(n+'-'+date+'.age' in fichiers for n in ('vision','mrjam_identite','sessions')):
        raise ValueError('Sauvegarde complète absente')
    valeur={'version':1,'date':date,'fichiers':fichiers,
            'registre_externe_recent_requis':True,'restauration_complete_verifiee':False}
    cible=root/('mrjam-'+date+'.json')
    fd=os.open(cible,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as f:json.dump(valeur,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)
    return valeur


def verifier(source,document):
    source=Path(source)
    valeur=json.loads(Path(document).read_text())
    if set(valeur)!={'version','date','fichiers','registre_externe_recent_requis','restauration_complete_verifiee'} or valeur['version']!=1:
        raise ValueError('Manifeste inconnu')
    date=valeur['date']
    datetime.datetime.strptime(date,'%Y-%m-%dT%H%M%SZ')
    if not isinstance(valeur['fichiers'],dict) or not 3<=len(valeur['fichiers'])<=10:raise ValueError('Jeu de fichiers invalide')
    for nom,sha in valeur['fichiers'].items():
        if not re.fullmatch(r'[a-z_-]+-'+re.escape(date)+r'\.age',nom) or not re.fullmatch(r'[a-f0-9]{64}',sha):
            raise ValueError('Nom ou empreinte invalide')
        fichier=source/nom
        if fichier.is_symlink() or not fichier.is_file() or empreinte(fichier)!=sha:raise ValueError('Copie modifiée ou absente')
    if not all(n+'-'+date+'.age' in valeur['fichiers'] for n in ('vision','mrjam_identite','sessions')):raise ValueError('Copie incomplète')
    return valeur


def copier(source,document,disque,cle,age='age'):
    source,disque,cle=Path(source),Path(disque),Path(cle)
    if disque.is_symlink() or not os.path.ismount(disque):raise ValueError('Disque monté requis ; ne pas copier sur le disque système par erreur')
    if cle.is_symlink() or cle.stat().st_mode&0o077:raise ValueError('Clé privée de restauration requise')
    valeur=verifier(source,document)
    destination=disque/'mrjam-sauvegardes'
    destination.mkdir(mode=0o700,exist_ok=True)
    if destination.is_symlink() or destination.stat().st_mode&0o077:raise ValueError('Répertoire de copies non privé')
    finale=destination/valeur['date']
    if finale.exists():raise ValueError('Cette génération est déjà copiée ; aucun écrasement')
    with tempfile.TemporaryDirectory(prefix='.copie-',dir=destination) as temporaire:
        root=Path(temporaire)
        for nom in valeur['fichiers']:
            copie=root/nom
            with (source/nom).open('rb') as entree, copie.open('xb') as sortie:
                shutil.copyfileobj(entree,sortie);sortie.flush();os.fsync(sortie.fileno())
            copie.chmod(0o600)
            if empreinte(copie)!=valeur['fichiers'][nom]:raise ValueError('Copie incomplète')
            subprocess.run([age,'--decrypt','-i',str(cle),str(copie)],stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL,check=True,timeout=600)
        cible=root/'manifest.json'
        cible.write_text(json.dumps(valeur,indent=2)+'\n');cible.chmod(0o600)
        fd=os.open(cible,os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)
        fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
        os.rename(root,finale)
        fd=os.open(destination,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
    return {'copie_chiffree_verifiee':True,'generation':valeur['date'],
            'restauration_complete_verifiee':False,'registre_proton_recent_requis':True}


if __name__=='__main__':
    os.umask(0o077)
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='operation',required=True)
    m=sub.add_parser('manifeste');m.add_argument('--repertoire',required=True);m.add_argument('--date',required=True)
    c=sub.add_parser('copier');c.add_argument('--source',required=True);c.add_argument('--manifeste',required=True);c.add_argument('--disque',required=True);c.add_argument('--cle',required=True)
    a=p.parse_args()
    if a.operation=='manifeste':
        r=manifeste(a.repertoire,a.date);print(json.dumps({'manifeste_cree':True,'fichiers':len(r['fichiers'])}))
    else:print(json.dumps(copier(a.source,a.manifeste,a.disque,a.cle)))
