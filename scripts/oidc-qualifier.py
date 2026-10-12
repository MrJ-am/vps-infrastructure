"""Qualification locale froide OIDC ; sources verrouillées, aucun serveur IdP."""
import argparse
from contextlib import ExitStack
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

RACINE = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sans-cache', action='store_true')
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--transactions', action='store_true')
    modes.add_argument('--transport', action='store_true')
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('sources_oidc', RACINE / 'scripts/oidc-verifier-sources.py')
    sources = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sources)
    sources.verifier(json.loads((RACINE / 'assemblage/oidc/dependances.lock.json').read_text()))
    if not os.environ.get('MRJAM_LIBCRYPTO') or not os.environ.get('SBCL_HOME'):
        raise ValueError('Environnement de qualification SBCL/DSO verrouillé requis')
    with ExitStack() as pile:
        dossier = pile.enter_context(tempfile.TemporaryDirectory(prefix='oidc-froid-', dir=RACINE / 'state'))
        env = dict(os.environ)
        fixture = None
        if args.transport:
            sys.path.insert(0, str(RACINE / 'tests'))
            from oidc_transport_fixture import Fixture
            fixture = pile.enter_context(Fixture())
            env['MRJAM_OIDC_FIXTURE'] = str(fixture.path)
        if args.sans_cache:
            env['ASDF_OUTPUT_TRANSLATIONS'] = '(:output-translations (t "' + dossier + '/") :ignore-inherited-configuration)'
        entree = ('tests/oidc-transport-froid.lisp' if args.transport else
                  'tests/oidc-transactions-froid.lisp' if args.transactions else 'tests/oidc-froid.lisp')
        resultat = subprocess.run(['sbcl', '--script', entree],
                                  cwd=RACINE, env=env, text=True, capture_output=True, timeout=180)
        # Les fixtures sont synthétiques ; sorties bornées et pas de credentials.
        if resultat.returncode:
            print(resultat.stderr[-3500:])
            print(resultat.stdout[-1200:])
            raise SystemExit(resultat.returncode)
        motif = (r'OIDC transport : (\d+) contrôles HTTPS réels terminés' if args.transport else
                 r'OIDC transactions : (\d+) contrôles terminés' if args.transactions else r'OIDC ES256 : (\d+) cas/assertions terminés')
        marqueur = ('Qualification du transport OIDC en image propre réussie.' if args.transport else
                    'Qualification des transactions OIDC en image propre réussie.' if args.transactions else 'Qualification OIDC dans une image propre réussie.')
        comptage = re.findall(motif, resultat.stdout)
        minimum = 32 if args.transport else 40 if args.transactions else 600
        if len(comptage) != 1 or int(comptage[0]) < minimum or resultat.stdout.count(marqueur) != 1:
            raise ValueError('Assertions OIDC non terminées')
        if fixture:
            fixture.verifier()
        print('Image de test propre : ' + comptage[0] + ' contrôles OIDC réussis ; cache ' + ('désactivé.' if args.sans_cache else 'ASDF incrémental.'))


if __name__ == '__main__':
    main()
