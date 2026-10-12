"""Qualification locale froide OIDC ; sources verrouillées, aucun serveur IdP."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

RACINE = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sans-cache', action='store_true')
    parser.add_argument('--transactions', action='store_true')
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('sources_oidc', RACINE / 'scripts/oidc-verifier-sources.py')
    sources = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sources)
    sources.verifier(json.loads((RACINE / 'assemblage/oidc/dependances.lock.json').read_text()))
    if not os.environ.get('MRJAM_LIBCRYPTO') or not os.environ.get('SBCL_HOME'):
        raise ValueError('Environnement de qualification SBCL/DSO verrouillé requis')
    with tempfile.TemporaryDirectory(prefix='oidc-froid-', dir=RACINE / 'state') as dossier:
        env = dict(os.environ)
        if args.sans_cache:
            env['ASDF_OUTPUT_TRANSLATIONS'] = '(:output-translations (t "' + dossier + '/") :ignore-inherited-configuration)'
        entree = 'tests/oidc-transactions-froid.lisp' if args.transactions else 'tests/oidc-froid.lisp'
        resultat = subprocess.run(['sbcl', '--script', entree],
                                  cwd=RACINE, env=env, text=True, capture_output=True, timeout=180)
        # Les fixtures sont synthétiques ; sorties bornées et pas de credentials.
        if resultat.returncode:
            print(resultat.stderr[-3500:])
            print(resultat.stdout[-1200:])
            raise SystemExit(resultat.returncode)
        motif = r'OIDC transactions : (\d+) contrôles terminés' if args.transactions else r'OIDC ES256 : (\d+) cas/assertions terminés'
        marqueur = 'Qualification des transactions OIDC en image propre réussie.' if args.transactions else 'Qualification OIDC dans une image propre réussie.'
        comptage = re.findall(motif, resultat.stdout)
        minimum = 36 if args.transactions else 600
        if len(comptage) != 1 or int(comptage[0]) < minimum or resultat.stdout.count(marqueur) != 1:
            raise ValueError('Assertions OIDC non terminées')
        print('Image de test propre : ' + comptage[0] + ' contrôles OIDC réussis ; cache ' + ('désactivé.' if args.sans_cache else 'ASDF incrémental.'))


if __name__ == '__main__':
    main()
