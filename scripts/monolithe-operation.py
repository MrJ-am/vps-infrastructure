"""Opérations fermées sur le descripteur central ; aucune commande libre."""
import importlib.util
import os
from pathlib import Path
import shlex
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('mrjam_stage',ROOT/'scripts/monolithe-stage.py')
stage=importlib.util.module_from_spec(spec);spec.loader.exec_module(stage)


def diagnostiquer(nixpkgs,revision):
    with (ROOT/'scripts/monolithe-diagnostic.py').open('rb') as f:
        stage.ssh('nix-shell -I nixpkgs='+nixpkgs+' -p python3 --run '+
                  shlex.quote('python3 -B - '+revision),stdin=f)


def main():
    stage.exiger(os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('GITHUB_REF')=='refs/heads/main',
                 'Opérateur réservé à la CI/CD centrale sur main')
    operation=os.environ.get('MRJAM_OPERATION');d=stage.descriptor();rev=d['revision_operateurs']
    stage.exiger(operation in ('restaurer','deployer','retour','diagnostic','confirmer-retour'),'Opération inconnue')
    if operation=='confirmer-retour':
        nixpkgs=stage.manifeste()['toolchain']['production']['nixpkgs']
        with (ROOT/'scripts/monolithe-retour-confirmer.py').open('rb') as f:
            stage.ssh('nix-shell -I nixpkgs='+nixpkgs+' -p python3 --run '+
                      shlex.quote('python3 -B - '+rev),stdin=f)
        return
    if operation=='diagnostic':
        nixpkgs=stage.manifeste()['toolchain']['production']['nixpkgs']
        diagnostiquer(nixpkgs,rev)
        return
    root=Path('/root/mrjam-assemblages')/rev/'payload/vps/scripts'
    commandes=[]
    if operation in ('restaurer','deployer'):
        commandes.append('python3 -B '+str(root/'monolithe-restaurer.py')+' '+rev)
    if operation in ('deployer','retour'):
        commandes.append('python3 -B '+str(root/'monolithe-activer.py')+' '+('activer' if operation=='deployer' else 'retour')+' '+rev)
    nixpkgs=stage.manifeste()['toolchain']['production']['nixpkgs']
    for commande in commandes:
        try:stage.ssh('nix-shell -I nixpkgs='+nixpkgs+' -p python3 --run '+shlex.quote(commande))
        except subprocess.CalledProcessError:
            # Lecture fermée dans le même run : ne pas rejouer l'opération ni
            # masquer son échec, même si son diagnostic est indisponible.
            try:diagnostiquer(nixpkgs,rev)
            except Exception as erreur:
                print('Diagnostic fermé indisponible : '+type(erreur).__name__,file=sys.stderr)
            raise


if __name__=='__main__':main()
