"""Vérifier sur téléphone une copie chiffrée, sans écrire ses données en clair."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tarfile

REFERENCE = 'vision-recuperation-20261010'
CLE_SHA256 = '86e1797da7805848ab8e56858f4308a483249c6130fc09cf23b45cd321673725'
REQUIS = {'vision.dump','identite.dump','sessions.sqlite','auth.htpasswd','acl.json','contexte.json'}
FACULTATIFS = {'effacements.jsonl','effacements-cycle.jsonl','effacements-communs.jsonl'}
MAXIMUM = 512*1024*1024


def verifier_archive(flux):
    with tarfile.open(fileobj=flux, mode='r|gz') as archive:
        membres = iter(archive)
        premier = next(membres)
        if premier.name != 'manifest.json' or not premier.isfile() or premier.size > 16384:
            raise ValueError('Manifeste initial requis')
        manifest = json.load(archive.extractfile(premier))
        if manifest.get('version') != 1 or manifest.get('reference') != REFERENCE or manifest.get('cle_publique_sha256') != CLE_SHA256 or manifest.get('bases_restaurees') is not True or manifest.get('sqlite_integrite') is not True:
            raise ValueError('Copie différente')
        fichiers = manifest.get('fichiers')
        if not isinstance(fichiers,dict) or not REQUIS <= set(fichiers) <= REQUIS|FACULTATIFS:
            raise ValueError('Copie incomplète')
        preuve = manifest.get('preuve')
        if not isinstance(preuve,str) or not re.fullmatch('[a-f0-9]{64}',preuve):
            raise ValueError('Preuve invalide')
        total = 0
        for valeur in fichiers.values():
            if not isinstance(valeur,dict) or set(valeur) != {'taille','sha256'} or type(valeur['taille']) is not int or not 0 <= valeur['taille'] <= MAXIMUM or not isinstance(valeur['sha256'],str) or not re.fullmatch('[a-f0-9]{64}',valeur['sha256']):
                raise ValueError('Empreinte invalide')
            total += valeur['taille']
        if total > MAXIMUM: raise ValueError('Copie trop grande')
        vus = set()
        for membre in membres:
            if membre.name not in fichiers or membre.name in vus or not membre.isfile() or membre.size != fichiers[membre.name]['taille']:
                raise ValueError('Archive différente')
            vus.add(membre.name)
            h = hashlib.sha256()
            with archive.extractfile(membre) as entree:
                for bloc in iter(lambda:entree.read(1024*1024),b''): h.update(bloc)
            if h.hexdigest() != fichiers[membre.name]['sha256']:
                raise ValueError('Contenu différent')
        if vus != set(fichiers): raise ValueError('Fichiers manquants')
    # Consommer la sortie AGE jusqu'à la fin : pas de succès sur un préfixe.
    while flux.read(1024*1024): pass
    return dict(reference=REFERENCE,fichiers_identiques_aux_copies_testees=True,
        donnees_en_clair_ecrites=False,preuve=preuve)


def verifier(chemin,cle,empreinte):
    if not re.fullmatch('[a-f0-9]{64}',empreinte): raise ValueError('Empreinte chiffrée invalide')
    h = hashlib.sha256()
    with Path(chemin).open('rb') as fichier:
        for bloc in iter(lambda:fichier.read(1024*1024),b''): h.update(bloc)
    if h.hexdigest() != empreinte: raise ValueError('Pièce jointe différente')
    info = Path(cle).lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.geteuid():
        raise ValueError('Clé privée locale requise')
    p = subprocess.Popen(['age','-d','-i',str(cle),str(chemin)],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
    try:
        resultat = verifier_archive(p.stdout)
        if p.wait(timeout=30) != 0: raise ValueError('Déchiffrement incomplet')
        return dict(resultat,dechiffrement_complet=True,copie_chiffree_sha256=empreinte)
    finally:
        p.stdout.close()
        if p.poll() is None: p.kill(); p.wait(timeout=10)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('copie'); p.add_argument('--cle',required=True); p.add_argument('--empreinte',required=True)
    a = p.parse_args()
    try: print(json.dumps(verifier(a.copie,a.cle,a.empreinte)))
    except Exception:
        print('Vérification refusée : fichier incomplet, accès refusé ou clé incorrecte. Aucun contenu privé affiché.',file=sys.stderr)
        sys.exit(1)
