"""Préparer exclusivement l'outillage déjà autorisé et ses locks centraux."""
import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from assemblage import RACINE, chemins_sources


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('operation',choices=['npm','python'])
    p.add_argument('--composant',choices=['vision','matheval','logique','style'])
    p.add_argument('--profil',choices=['navigateur','signature','logo','embeddings'])
    args=p.parse_args()
    subprocess.run([sys.executable,str(RACINE/'scripts/verifier-dependances.py')],check=True)
    d=json.loads((RACINE/'assemblage/dependances.json').read_text())
    sources=chemins_sources(atelier=os.environ.get('MRJAM_ATELIER'))
    if args.operation=='npm':
        if not args.composant:p.error('--composant requis')
        for lock in d['npm_verrouille']:
            if lock['composant']!=args.composant:continue
            dossier=(sources[args.composant]/lock['lock']).parent
            subprocess.run(['npm','ci','--ignore-scripts','--no-audit','--no-fund'],cwd=dossier,check=True)
        # Un seul compilateur Elm 0.19.1 déjà autorisé. Le paquet historique elm
        # de l'atelier téléchargeait un exécutable hors du lock npm ; réutiliser
        # l'archive native @lydell verrouillée plutôt que relancer ce downloader.
        if args.composant=='style':
            compiler=sources['style']/'node_modules/.bin/elm'
            version=subprocess.check_output([compiler,'--version'],text=True).strip()
            if version!='0.19.1':raise ValueError('Compilateur Elm différent')
            lien=sources['style']/'ateliers/logo/node_modules/.bin/elm'
            if not lien.is_symlink():raise ValueError('Entrée npm elm inattendue')
            lien.unlink();lien.symlink_to(compiler.resolve())
    else:
        if not args.profil:p.error('--profil requis')
        profile=d['python_profils'][args.profil]
        if sys.version_info[:2]!=(3,12) or platform.system()!='Linux' or platform.machine()!='x86_64':
            raise ValueError('Les roues verrouillées exigent Python 3.12 Linux x86_64 ; aucun autre runtime installé')
        cible=RACINE/'state/outils-python'/args.profil
        if not cible.exists():subprocess.run([sys.executable,'-m','venv',cible],check=True)
        if cible.is_symlink() or not (cible/'pyvenv.cfg').is_file():raise ValueError('Environnement Python inattendu')
        subprocess.run([cible/'bin/python','-m','pip','install','--require-hashes','--only-binary=:all:',
                        '--index-url','https://pypi.org/simple','-r',RACINE/profile['fichier']],check=True)
        print(json.dumps({'profil':args.profil,'activation':'PATH='+str(cible/'bin')+':$PATH',
                          'lock_sha256':profile['sha256']},ensure_ascii=False))


if __name__=='__main__':main()
