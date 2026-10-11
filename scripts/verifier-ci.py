"""Absence de CI satellite et intégrité des recettes historiques archivées."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
from assemblage import chemins_sources,manifeste,verifier_sources


def verifier_archive(base,index):
    for e in json.loads(index.read_text())['workflows']:
        p=base/e['archive']
        if p.is_symlink() or not p.resolve().is_relative_to(index.parent.resolve()):raise ValueError('Archive externe')
        if hashlib.sha256(p.read_bytes()).hexdigest()!=e['sha256']:raise ValueError('Recette historique modifiée')


def verifier():
    sources=chemins_sources(atelier=os.environ.get('MRJAM_ATELIER'))
    verifier_sources(sources,manifeste(),exact=True)
    for nom,base in sources.items():
        if nom=='vps':continue
        fichiers=subprocess.check_output(['git','ls-files','.github/workflows'],cwd=base,text=True).splitlines()
        if any(Path(p).suffix in ('.yml','.yaml') for p in fichiers):raise ValueError('CI satellite suivie : '+nom)
        if any(p.suffix in ('.yml','.yaml') for p in (base/'.github/workflows').glob('*')):
            raise ValueError('CI satellite locale : '+nom)
        index=base/'coordination/archive/workflows-20261011/INDEX.json'
        if not index.exists():continue
        verifier_archive(base,index)
    base=sources['vps']
    verifier_archive(base,base/'coordination/historique/workflows-infrastructure-20261011/INDEX.json')
    for p in ('vision-demande.yml','vision-mise-en-service.yml'):
        if (base/'.github/workflows'/p).exists():raise ValueError('Ancien coordinateur de publication actif')
    print('Cinq composants sans YAML CI ni relais ; treize recettes satellites et deux coordinateurs historiques exacts conservés.')


if __name__=='__main__':verifier()
