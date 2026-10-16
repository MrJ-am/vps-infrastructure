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
    operation=os.environ.get('MRJAM_OPERATION')
    if operation in ('forgejo-preparer','forgejo-deployer','forgejo-retour'):
        spec=importlib.util.spec_from_file_location('forgejo_operation',ROOT/'scripts/forgejo-operation.py')
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        m.main();return
    if operation=='forgejo-diagnostic':
        with (ROOT/'scripts/forgejo-diagnostic.py').open('rb') as f:
            stage.ssh('nix-shell -I nixpkgs='+stage.manifeste()['toolchain']['production']['nixpkgs']+
                      ' -p python3 --run '+shlex.quote('python3 -B -'),stdin=f)
        return
    if operation=='reconnexion-outillage':
        spec=importlib.util.spec_from_file_location('outillage_reconnexion',ROOT/'scripts/mcp-reconnexion-outillage.py')
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        m.main();return
    if operation in ('reconnexion-preparer','reconnexion-deployer'):
        spec=importlib.util.spec_from_file_location('stage_reconnexion',ROOT/'scripts/log-interface-stage.py')
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        m.main('reconnexion',activer=operation=='reconnexion-deployer');return
    if operation in ('reconnexion-diagnostic','reconnexion-retour'):
        p=__import__('json').loads((ROOT/'operations/mcp-reconnexion-candidat.json').read_text());cible=p['revision_sources']
        stage.exiger(__import__('re').fullmatch('[a-f0-9]{40}',cible),'Révision invalide')
        root=Path('/root/mrjam-corrections/reconnexion')/cible
        phase='diagnostic' if operation=='reconnexion-diagnostic' else 'retour'
        stage.ssh('nix-shell -I nixpkgs='+stage.manifeste()['toolchain']['production']['nixpkgs']+
          ' -p python3 --run '+shlex.quote('python3 -B '+str(root/'payload/promouvoir.py')+' '+phase+' '+cible));return
    if operation=='audition-diagnostic':
        p=__import__('json').loads((ROOT/'operations/audition-candidat.json').read_text());cible=p['revision_sources']
        stage.exiger(__import__('re').fullmatch('[a-f0-9]{40}',cible),'Révision de diagnostic invalide')
        with (ROOT/'scripts/audition-diagnostic.py').open('rb') as f:
            stage.ssh('nix-shell -I nixpkgs='+stage.manifeste()['toolchain']['production']['nixpkgs']+
                      ' -p python3 --run '+shlex.quote('python3 -B - '+cible),stdin=f)
        return
    if operation in ('audition-preparer','audition-deployer'):
        spec=importlib.util.spec_from_file_location('stage_audition',ROOT/'scripts/log-interface-stage.py')
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        m.main('audition',activer=operation=='audition-deployer');return
    if operation=='audition-retour':
        p=__import__('json').loads((ROOT/'operations/audition-candidat.json').read_text());cible=p['revision_sources']
        stage.exiger(__import__('re').fullmatch('[a-f0-9]{40}',cible),'Révision de retour invalide')
        root=Path('/root/mrjam-corrections/audition')/cible
        stage.ssh('nix-shell -I nixpkgs='+stage.manifeste()['toolchain']['production']['nixpkgs']+
          ' -p python3 --run '+shlex.quote('python3 -B '+str(root/'payload/promouvoir.py')+' retour '+cible));return
    d=stage.descriptor();rev=d['revision_operateurs']
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
