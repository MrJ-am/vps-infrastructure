"""Vérifier un lot public du store sans lancer ses services ni lire de credential."""
import argparse
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys

UTILISATEURS = {'keycloak': 'keycloak', 'mrj-auth': 'mrj-auth',
    'vision-gestion': 'vision_administration', 'vision-cycle': 'vision_cycle',
    'mrjam-admission': 'vision_admission', 'mrjam-fermeture': 'vision_fermeture',
    'mrjam-courriel': 'mrjam-courriel'}
IMPORTS = '''import importlib.util,os,pathlib,sys
if os.geteuid()==0:raise RuntimeError('Qualification sans privilege requise')
def proteger(evenement,args):
    if evenement in ('socket.connect','socket.bind','sqlite3.connect','subprocess.Popen'):
        raise PermissionError('Effet interdit pendant les imports')
sys.addaudithook(proteger)
p=pathlib.Path(sys.argv[1]);sys.path.insert(0,str(p.parent))
fichiers=[p]
if sys.argv[2]=='mrj-auth':fichiers.append(p.parent/'oidc.py')
for numero,fichier in enumerate(fichiers):
    nom='qualification_import_'+str(numero)
    spec=importlib.util.spec_from_file_location(nom,fichier)
    module=importlib.util.module_from_spec(spec);sys.modules[nom]=module
    spec.loader.exec_module(module)
sys.stdout.write('imports_ok\\n')
'''


def exiger(condition, raison):
    if not condition: raise ValueError(raison)


def chemin_store(chemin):
    exiger(isinstance(chemin, str) and re.fullmatch(
        r'/nix/store/[0-9a-z]{32}-[A-Za-z0-9._+-]{1,150}(?:/[A-Za-z0-9._+-]+)*', chemin) and
        '..' not in Path(chemin).parts, 'Chemin store inattendu')
    return Path(chemin)


def verifier_resume(resume, *, epingle=True):
    exiger(resume['version'] == 1 and resume['keycloak_version'] == '26.7.3' and
        resume['jdbc_unix'] is True and resume['garde_activation'] is True and
        all(resume[k] is False for k in ('generation_constructible', 'preconditions_validees',
            'inscriptions', 'postgres_tcp', 'activation')) and
        (not epingle or resume['fournisseur_epingle'] is True), 'Garde-fou ou socle inattendu')
    for cle in ('lot', 'keycloak', 'sources'): chemin_store(resume[cle])
    if epingle: chemin_store(resume['fournisseur_source'])
    exiger(set(resume['unites']) == set(UTILISATEURS), 'Liste de composants inattendue')
    for nom, unite in resume['unites'].items():
        chemin_store(unite['chemin'])
        exiger(unite['utilisateur'] == UTILISATEURS[nom], 'Utilisateur de service différent')
        args = shlex.split(unite['executable'])
        exiger(args and chemin_store(args[0]), 'Exécutable absent')
        if nom != 'keycloak':
            exiger(len(args) == 2 and args[0].endswith('/bin/python3') and
                   chemin_store(args[1]).suffix == '.py', 'Commande Python inattendue')


def executer(args):
    r = subprocess.run(args, capture_output=True, timeout=60)
    exiger(r.returncode == 0, 'Import natif refusé')
    return r.stdout.decode()


def verifier(resume, *, commande=executer, epingle=True):
    verifier_resume(resume, epingle=epingle)
    lot = chemin_store(resume['lot'])
    exiger(lot.is_dir() and not (lot / 'bin/switch-to-configuration').exists(), 'Lot non conforme')
    for nom, unite in resume['unites'].items():
        cible = lot / 'unites' / (nom + '.service')
        exiger(cible.is_symlink() and str(cible.resolve()) == unite['chemin'] and
            (cible / (nom + '.service')).is_file(), 'Unité construite différente')
        args = shlex.split(unite['executable'])
        exiger(Path(args[0]).is_file(), 'Exécutable non construit')
        if nom != 'keycloak':
            exiger(Path(args[1]).is_file(), 'Source Python non construite')
            appel = ['env', '-i', 'PATH=/run/current-system/sw/bin:/usr/bin:/bin',
                'PYTHONDONTWRITEBYTECODE=1', args[0], '-I', '-c', IMPORTS, args[1], nom]
            if os.geteuid() == 0: appel = ['runuser', '-u', 'nobody', '--', *appel]
            exiger(commande(appel).strip() == 'imports_ok', 'Résultat des imports inattendu')
    exiger(str((lot / 'keycloak').resolve()) == resume['keycloak'] and
        str((lot / 'sources').resolve()) == resume['sources'] and
        (lot / 'sources/services-mrjam.tar.gz').is_file(), 'Sources ou paquet construits différents')
    return {'unites_construites': len(UTILISATEURS), 'imports_python': len(UTILISATEURS) - 1,
            'imports_sans_privilege': True, 'generation_constructible': False, 'activation': False}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('resume'); p.add_argument('--qualification-locale', action='store_true'); a = p.parse_args()
    try:
        print(json.dumps(verifier(json.loads(Path(a.resume).read_text()), epingle=not a.qualification_locale)))
    except Exception: p.exit(1, 'Vérification des composants refusée ; aucun détail privé affiché.\n')
