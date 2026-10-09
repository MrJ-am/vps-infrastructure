"""Classer les journaux privés du seul essai Unix identifié, sans mutation."""
import json
import os
from pathlib import Path
import re
import stat

REVISION = 'ebf5a5bfb65fdb0e479e1bc3717d8e6e0d3986d7'
DOSSIER = Path('/root/vision-identite-unix-operations') / REVISION
MOTIFS = {
    'permission_refusee': r'(?m)^.*(?:Permission denied|Operation not permitted)',
    'lanceur_postgresql_non_traversable': r'(?m)^.*?/run/mrjam-q-source-' + REVISION[:12] + r'/postgresql\.sh:.*Permission denied',
    'socket_synthetique_absent': r'(?m)^.*?\.s\.PGSQL\.5432.*No such file or directory',
    'lanceur_absent': r'(?m)^.*?/run/mrjam-q-source-' + REVISION[:12] + r'/(?:postgresql|demarrer)\.sh:.*No such file or directory',
    'systeme_fichiers_lecture_seule': r'(?m)^.*Read-only file system',
    'initdb_refuse': r'(?m)^initdb: error:',
    'postgresql_fatal': r'(?m)^.*(?:FATAL:|PANIC:)',
    'espace_insuffisant': r'(?m)^.*No space left on device',
    'connexion_refusee': r'(?m)^.*Connection refused',
    'authentification_peer_refusee': r'(?m)^.*peer authentication failed',
    'http_synthetique_refuse': r'(?m)^\{"http_synthetique": false,',
    'delai_depasse': r'Délai de qualification dépassé',
}


def classer(contenu):
    return {'categories': [nom for nom, motif in MOTIFS.items() if re.search(motif, contenu)],
        'contenu_affiche': False}


def lire(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise ValueError('Journal privé requis')
        if info.st_size > 262144: raise ValueError('Journal trop grand')
        return os.read(fd, 262144).decode('utf-8', errors='replace')
    finally: os.close(fd)


def main():
    if os.geteuid() != 0: raise ValueError('Audit Actions root requis')
    for path in (DOSSIER.parent, DOSSIER):
        info = path.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077:
            raise ValueError('Dossier privé requis')
    resultat = dict(audit_unix=1, revision=REVISION, activation=False)
    for nom, fichier in (('operateur', 'diagnostic-prive.log'), ('postgresql', 'pg-prive.log'), ('identite', 'idp-prive.log')):
        texte = lire(DOSSIER / fichier)
        resultat[nom] = dict(journal_vide=not bool(texte.strip()), **classer(texte))
    resultat['rapport_present'] = (DOSSIER / 'qualification.json').is_file()
    print(json.dumps(resultat), flush=True)


if __name__ == '__main__':
    try: main()
    except Exception:
        print(json.dumps(dict(audit_unix=1, diagnostic_refuse=True, activation=False)))
        raise SystemExit(1)
