"""Promotion Log fermée dans la CI centrale ; aucun test de développement distant."""
import importlib.util
import os
from pathlib import Path
import shlex
import subprocess

ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('stage_log',ROOT/'scripts/monolithe-stage.py')
stage=importlib.util.module_from_spec(s);s.loader.exec_module(stage)

def main():
    stage.exiger(os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('GITHUB_REF')=='refs/heads/main',
                 'Opérateur réservé à la CI centrale main')
    op=os.environ.get('MRJAM_OPERATION')
    stage.exiger(op in ('preparer','deployer','courriel','retour','diagnostic'),'Opération Log inconnue')
    if op in ('preparer','deployer'): stage.main('log')
    if op=='preparer': return
    d=stage.descriptor('log');rev=d['revision_operateurs']
    root=Path('/root/mrjam-assemblages')/rev/'payload/vps/scripts'
    if op=='diagnostic':
        cmd='python3 - '+rev
        stage.ssh('nix-shell -I nixpkgs='+stage.manifeste()['toolchain']['production']['nixpkgs']+
                  ' -p python3 --run '+shlex.quote(cmd),input=(ROOT/'scripts/log-diagnostic.py').read_bytes())
        return
    commandes=[]
    if op=='deployer': commandes.append('python3 -B '+str(root/'monolithe-restaurer.py')+' '+rev)
    commandes.append('python3 -B '+str(root/'log-activer.py')+' '+{'deployer':'activer','retour':'retour','courriel':'courriel'}[op]+' '+rev)
    for cmd in commandes:
        stage.ssh('nix-shell -I nixpkgs='+stage.manifeste()['toolchain']['production']['nixpkgs']+
                  ' -p python3 --run '+shlex.quote(cmd))

if __name__=='__main__': main()
