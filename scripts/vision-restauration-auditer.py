"""Classer le refus d'un seul essai privé, sans publier son journal.

Lecture seule depuis Actions : ni SQL, ni nouvelle tentative de restauration.
La sortie suit une liste fermée de catégories et de booléens.
"""
import json
import os
from pathlib import Path
import re
import stat

REVISION = 'bb26c11a3afd5b924b91c579cc5fc5cd7841d3df'
DOSSIER = Path('/root/vision-multiutilisateur-operations') / REVISION
MOTIFS = {
    'role_absent': r'(?m)^.*(?:ERROR:|ERREUR:)\s+role "[^"\n]{1,200}" does not exist\s*$',
    'extension_vector_absente': r'(?m)^.*ERROR:\s+extension "vector" is not available\s*$',
    'extension_trgm_absente': r'(?m)^.*ERROR:\s+extension "pg_trgm" is not available\s*$',
    'creation_base_en_transaction': r'(?m)^.*ERROR:\s+CREATE DATABASE cannot run inside a transaction block\s*$',
    'collation_incompatible': r'(?m)^.*ERROR:\s+(?:new collation|new locale|encoding).*does not match.*$',
    'permission_refusee': r'(?m)^(?:psql|pg_restore):.*(?:Permission denied|ERROR:\s+permission denied for [^\n]{1,200})\s*$',
    'socket_inaccessible': r'(?m)^(?:psql|pg_restore):.*connection to server on socket.*failed:.*$',
    'archive_incompatible': r'(?m)^pg_restore: error: unsupported version \([0-9.]+\) in file header\s*$',
}


def classer(contenu):
    # Les lignes SQL et la traceback ne sont jamais restituées. Une erreur
    # inconnue reste inconnue ; aucune déduction par simple mot présent.
    return {'categories': [nom for nom, motif in MOTIFS.items() if re.search(motif, contenu)],
        'refus_psql': bool(re.search(r'(?m)^psql:(?:<stdin>:[0-9]+:| error:)', contenu)),
        'refus_pg_restore': bool(re.search(r'(?m)^pg_restore: error:', contenu))}


def lire(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise ValueError('Journal privé requis')
        if info.st_size > 262144: raise ValueError('Journal trop grand')
        return os.read(fd, 262144).decode('utf-8', errors='replace')
    finally:
        os.close(fd)


def main():
    if os.geteuid() != 0: raise ValueError('Audit Actions root requis')
    info = DOSSIER.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077:
        raise ValueError('Dossier privé requis')
    resultat = {'audit_restauration': 1, 'revision': REVISION, 'activation': False,
        **classer(lire(DOSSIER / 'diagnostic-prive.log'))}
    resultat['presence'] = {nom: (DOSSIER / chemin).is_file() for nom, chemin in {
        'evaluation': 'systeme-actif.json', 'configuration': 'nixos-avant.tar',
        'acl': 'acl-avant.json', 'empreintes': 'empreintes-privees.json',
        'dump_clair': 'vision.dump', 'dump_age': 'vision.dump.age',
        'retour': 'retour-acl.sql', 'rapport': 'preparation.json'}.items()}
    print(json.dumps(resultat, ensure_ascii=False))


if __name__ == '__main__':
    try: main()
    except Exception:
        print(json.dumps({'audit_restauration': 1, 'diagnostic_refuse': True, 'activation': False}))
        raise SystemExit(1)
