"""Génération et contrôles documentaires Vision dans un checkout propre possédé."""
import os
from pathlib import Path
import subprocess
import tempfile
from assemblage import RACINE,chemins_sources,manifeste,verifier_sources

sources=chemins_sources(atelier=os.environ.get('MRJAM_ATELIER'))
verifier_sources(sources,manifeste(),exact=True)
parent=RACINE/'state/ateliers-vision';parent.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory(prefix='contrats-',dir=parent) as tmp:
    atelier=Path(tmp)/'source'
    subprocess.run(['git','worktree','add','--quiet','--detach',atelier,manifeste()['sources']['vision']['revision']],cwd=sources['vision'],check=True)
    try:
        for commande in [['python3','scripts/contrats.py'],['git','diff','--exit-code','--','docs/outils.json','docs/openapi.json'],
            ['python3','tests/check_openapi.py'],['python3','-m','unittest','discover','-s','tests','-p','test_client_catalog.py'],
            ['python3','-m','unittest','discover','-s','tests','-p','test_contrat_tutoriel.py']]:
            subprocess.run(commande,cwd=atelier,check=True)
    finally:subprocess.run(['git','worktree','remove','--force',atelier],cwd=sources['vision'],check=True)
