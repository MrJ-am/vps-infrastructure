"""Compiler sans privilège avec des ressources en lecture seule, comme Nix."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def verifier(librairies):
    if os.geteuid() == 0: raise ValueError('Qualification sans privilège requise')
    with tempfile.TemporaryDirectory() as d:
        atelier = Path(d); source = atelier / 'source'
        shutil.copytree(ROOT / 'services/keycloak-mrjam', source)
        ressources = source / 'resources'
        for p in ressources.rglob('*'): p.chmod(0o555 if p.is_dir() else 0o444)
        ressources.chmod(0o555)
        temporaire = atelier / 'temp'; temporaire.mkdir()
        sortie = atelier / 'mrjam-identite.jar'
        try:
            subprocess.run(['sh', str(source / 'compiler.sh'), str(librairies), str(sortie)],
                env={**os.environ, 'TMPDIR': str(temporaire)}, check=True)
            assert not list(temporaire.iterdir()), 'La compilation doit retirer ses fichiers temporaires'
            with zipfile.ZipFile(sortie) as jar:
                assert 'META-INF/services/org.keycloak.email.EmailSenderProviderFactory' in jar.namelist()
                assert 'org/mrjam/identite/CourrielSecurise.class' in jar.namelist()
            assert all(not p.stat().st_mode & 0o222 for p in [ressources, *ressources.rglob('*')]), \
                'La source doit rester en lecture seule'
            print('Compilation sans privilège : ressources conservées et copie temporaire effacée.')
        finally:
            for p in [ressources, *ressources.rglob('*')]: p.chmod(p.stat().st_mode | 0o200)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--librairies', required=True, type=Path)
    verifier(p.parse_args().librairies.resolve())
