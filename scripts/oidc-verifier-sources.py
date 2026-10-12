"""Vérifier les sources Nix auditées avant leur chargement ASDF, sans installation."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

RACINE = Path(__file__).resolve().parents[1]


def verifier(lock):
    attendus = {'ironclad', 'cl-base64', 'bordeaux-threads', 'alexandria',
                'global-vars', 'trivial-features', 'trivial-garbage'}
    bibliotheques = lock['bibliotheques']
    if len(bibliotheques) != len(attendus) or {b['name'] for b in bibliotheques} != attendus:
        raise ValueError('Graphe OIDC différent de son audit')
    if (lock['nixpkgs_revision'], lock['sbcl'], lock['asdf']) != (
            'c5c4a43b0e8056328ec4529f735cabdb8f1942bb', '2.6.4', '3.3.1'):
        raise ValueError('Toolchain OIDC différente de son audit')
    nix_hash = '/home/agent/.nix-profile/bin/nix-hash'
    if not Path(nix_hash).is_file():
        nix_hash = 'nix-hash'
    for b in bibliotheques:
        if (not re.fullmatch(r'/nix/store/[a-z0-9]{32}-[^/]+', b['src'])
                or not re.fullmatch(r'[a-z0-9]{52}', b['hash'])
                or b['nar_sha256'] != 'sha256:' + b['hash']
                or not set(b['deps']).issubset(attendus)):
            raise ValueError('Source OIDC non verrouillée')
        source = Path(b['src'])
        if not source.is_dir() or source.is_symlink():
            raise ValueError('Source OIDC absente ou redirigée')
        resultat = subprocess.check_output([nix_hash, '--type', 'sha256', '--base32', str(source)], text=True).strip()
        if resultat != b['hash']:
            raise ValueError('NAR différent : ' + b['name'])
        for relatif, sha in b['licences_fichiers'].items():
            fichier = source / relatif
            if fichier.is_symlink() or not fichier.resolve().is_relative_to(source):
                raise ValueError('Licence extérieure')
            if hashlib.sha256(fichier.read_bytes()).hexdigest() != sha:
                raise ValueError('Licence différente : ' + b['name'])
    print('OIDC : sept sources/licences Nix exactes ; aucun téléchargement.')


if __name__ == '__main__':
    verifier(json.loads((RACINE / 'assemblage/oidc/dependances.lock.json').read_text()))
