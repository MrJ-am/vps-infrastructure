"""Inventaire privé des seuls identifiants historiques, sans contenu pédagogique."""
import json
import os
from pathlib import Path
import re
import stat

IDENTIFIANT = re.compile(r'[A-Za-z0-9_.-]{1,64}')


def exiger(condition):
    if not condition: raise ValueError('Rattachement historique ambigu ou non conforme')


def identifiants_auth(path, uid, gid):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        st = os.fstat(fd)
        exiger(stat.S_ISREG(st.st_mode) and st.st_uid == uid and st.st_gid == gid and
            st.st_nlink == 1 and stat.S_IMODE(st.st_mode) in (0o600, 0o640) and st.st_size <= 16384)
        contenu = os.read(fd, 16385).decode('utf-8')
        exiger(len(contenu.encode()) <= 16384)
    finally: os.close(fd)
    comptes, vus = [], set()
    for ligne in contenu.splitlines():
        exiger(ligne.count(':') == 1)
        nom, empreinte = ligne.split(':')
        exiger(IDENTIFIANT.fullmatch(nom) and nom not in vus)
        vus.add(nom)
        if empreinte.startswith('!') or empreinte == '*': continue
        # Le format historique est vérifié sans publier ni conserver le hash.
        exiger(re.fullmatch(r'\$6\$(?:rounds=[0-9]+\$)?[./A-Za-z0-9]{1,16}\$[./A-Za-z0-9]{86}', empreinte))
        comptes.append(nom)
    exiger(len(comptes) == 1)
    return comptes


def inspecter(requete, comptes_auth):
    """requete utilise une seule transaction REPEATABLE READ READ ONLY."""
    exiger(isinstance(comptes_auth, list) and len(comptes_auth) == 1 and
        isinstance(comptes_auth[0], str) and IDENTIFIANT.fullmatch(comptes_auth[0]))
    tables = json.loads(requete("""SELECT coalesce(json_agg(table_name ORDER BY table_name),'[]')
      FROM information_schema.columns WHERE table_schema='public'
      AND column_name='utilisateur' AND table_name LIKE 'vision_%'"""))
    exiger(isinstance(tables, list) and 1 <= len(tables) <= 200 and
        len(set(tables)) == len(tables) and 'vision_profils' in tables and
        all(isinstance(t, str) and re.fullmatch(r'vision_[a-z0-9_]{1,70}', t) for t in tables))
    proprietaires = set()
    for table in tables:
        # Nom borné issu du catalogue ; aucune autre colonne n'est lue.
        noms = json.loads(requete('SELECT coalesce(json_agg(utilisateur),\'[]\') FROM '
            '(SELECT DISTINCT utilisateur FROM public."' + table + '" LIMIT 2) t'))
        exiger(isinstance(noms, list) and len(noms) <= 1 and
            all(isinstance(u, str) and IDENTIFIANT.fullmatch(u) for u in noms))
        if table == 'vision_profils': exiger(noms == comptes_auth)
        proprietaires.update(noms)
    exiger(proprietaires == set(comptes_auth))
    return dict(version=1, utilisateur_historique=comptes_auth[0],
        proprietaires=1, tables_personnelles=len(tables), authentification_unique=True)


def public(rapport):
    # Liste explicite : aucun identifiant, hash, titre, note ou email.
    return {k: rapport[k] for k in ('proprietaires', 'tables_personnelles', 'authentification_unique')}
