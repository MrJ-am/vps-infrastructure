"""Assertions de routage/séparation locales, aucune construction système."""
from pathlib import Path
import subprocess
import json
ROOT=Path(__file__).resolve().parents[1]
if __name__=='__main__':
    base=ROOT/'state/outils-sources/nixpkgs-c5c4a43b0e8056328ec4529f735cabdb8f1942bb'
    if not base.is_dir(): raise ValueError('Nixpkgs verrouillé requis')
    nix='/home/agent/.nix-profile/bin/nix-instantiate'
    if not Path(nix).is_file(): nix='nix-instantiate'
    r=subprocess.run([nix,'--eval','--strict','--json','-I','nixpkgs='+str(base),
                      'tests/log-nix.nix'],cwd=ROOT,capture_output=True,text=True,check=True,timeout=60)
    d=json.loads(r.stdout)
    if d!={'kanidmSepare':True,'clientLisp':True,'keycloakActif':False,'tlsVerifie':True,'processusMetier':1,'production':False}:
        raise ValueError('Configuration Log non conforme')
    print(r.stdout.strip())
