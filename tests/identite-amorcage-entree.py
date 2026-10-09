"""Comparer l'entrée persistante à l'expression de préparation, sans construction."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('essai_entree', ROOT/'scripts/vision-identite-amorcage-activer.py')
m=importlib.util.module_from_spec(s); s.loader.exec_module(m)


def evaluer(fichier, configuration, attr=None):
    args=['nix-instantiate','--eval','--strict','--json',str(ROOT/'scripts'/fichier),
        '--argstr','configuration',str(configuration)]
    if attr: args+=['--attr',attr]
    return json.loads(subprocess.check_output(args))


with tempfile.TemporaryDirectory() as tmp:
    original=ROOT/'hosts/hostinger/logique.nix'
    attendu=evaluer('vision-identite-amorcage.nix',original,'resume')['systeme_amorcage']
    entry=Path(tmp)/'entree.nix'
    entry.write_text(m.entree_nix(original,ROOT/'modules/identite-amorcage.nix',None))
    assert evaluer('vision-identite-amorcage-systeme.nix',entry)==attendu
    print(json.dumps({'entree_persistante_identique': True, 'activation': False}))
