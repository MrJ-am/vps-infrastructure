"""Qualifier la correction HTTP réelle et sa superposition Native, localement."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]

def verifier():
    s=importlib.util.spec_from_file_location('connexion_operateur',ROOT/'scripts/log-connexion-promouvoir.py')
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
    base=ROOT/'state/outils-sources/nixpkgs-c5c4a43b0e8056328ec4529f735cabdb8f1942bb'
    # disabledModules de la fixture retire l'import canonique dans sa base.
    # Superposer les mêmes octets sous un chemin indépendant, comme le VPS
    # actuel dont la génération précédente n'importe pas ce nouveau fichier.
    with tempfile.TemporaryDirectory(prefix='mrjam-log-referrer-') as tmp:
        correction=Path(tmp)/'log-referrer.nix'
        correction.write_bytes((ROOT/'modules/log-referrer.nix').read_bytes())
        ex='import ./scripts/log-connexion-evaluation.nix { configuration='+json.dumps(str(ROOT/'tests/log-connexion-base.nix'))+'; correction='+json.dumps(str(correction))+'; }'
        result=subprocess.run(['nix-instantiate','--eval','--strict','--json','-I','nixpkgs='+str(base),'--expr',ex],
          cwd=ROOT,capture_output=True,text=True,timeout=120)
    if result.returncode:
        diagnostic=ROOT/'state/log-connexion-evaluation.log';diagnostic.write_text(result.stderr)
        raise ValueError('Évaluation locale refusée ; diagnostic dans state/log-connexion-evaluation.log')
    r=json.loads(result.stdout)
    m.verifier_evaluation(r,dict(generation=r['avant'],demarrage=r['avant']))
    if r['avant']==r['apres']:raise ValueError('Correction sans effet sur la génération')
    sys.path.insert(0,str(ROOT/'tests'))
    s=importlib.util.spec_from_file_location('connexion_navigateur',ROOT/'tests/log-referrer-navigateur.py')
    navigateur=importlib.util.module_from_spec(s);s.loader.exec_module(navigateur);navigateur.verifier()
    print(json.dumps({'superposition_native':True,'services_et_routes_proteges':True,'production':False}))

if __name__=='__main__':verifier()
