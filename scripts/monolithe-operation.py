"""Opérations fermées sur le descripteur central ; aucune commande libre."""
import importlib.util
import os
from pathlib import Path
import shlex
import subprocess

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('mrjam_stage',ROOT/'scripts/monolithe-stage.py')
stage=importlib.util.module_from_spec(spec);spec.loader.exec_module(stage)


def main():
    stage.exiger(os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('GITHUB_REF')=='refs/heads/main',
                 'Opérateur réservé à la CI/CD centrale sur main')
    operation=os.environ.get('MRJAM_OPERATION');d=stage.descriptor();rev=d['revision_operateurs']
    stage.exiger(operation in ('restaurer','deployer','retour'),'Opération inconnue')
    root=Path('/root/mrjam-assemblages')/rev/'payload/vps/scripts'
    commandes=[]
    if operation in ('restaurer','deployer'):
        commandes.append('python3 -B '+str(root/'monolithe-restaurer.py')+' '+rev)
    if operation in ('deployer','retour'):
        commandes.append('python3 -B '+str(root/'monolithe-activer.py')+' '+('activer' if operation=='deployer' else 'retour')+' '+rev)
    nixpkgs=stage.manifeste()['toolchain']['production']['nixpkgs']
    for commande in commandes:stage.ssh('nix-shell -I nixpkgs='+nixpkgs+' -p python3 --run '+shlex.quote(commande))


if __name__=='__main__':main()
