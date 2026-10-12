"""Une seconde version commune doit bloquer, même dans une transitive npm."""
import copy
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
spec = importlib.util.spec_from_file_location('dependances', ROOT / 'scripts/verifier-dependances.py')
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)


class Versions(unittest.TestCase):
    def setUp(self):
        self.inventory = {
            'versions_communes_outillage': {'python': {'playwright': '1.61.0'}},
            'python_profils': {
                'a': {'paquets': [{'nom': 'playwright', 'version': '1.61.0'},
                                   {'nom': 'paquet_commun', 'version': '2'}]},
                'b': {'paquets': [{'nom': 'playwright', 'version': '1.61.0'},
                                   {'nom': 'Paquet-Commun', 'version': '2'}]},
            },
        }

    def test_profils_communs_conformes(self):
        d.verifier_versions_python(self.inventory)

    def test_divergence_transitive_normalisee_refusee(self):
        self.inventory['python_profils']['b']['paquets'][1]['version'] = '3'
        with self.assertRaisesRegex(ValueError, 'parallèles'):
            d.verifier_versions_python(self.inventory)

    def test_tous_profils_anciens_refuses(self):
        for profil in self.inventory['python_profils'].values():
            profil['paquets'][0]['version'] = '1.57.0'
        with self.assertRaisesRegex(ValueError, 'socle commun'):
            d.verifier_versions_python(self.inventory)

    def test_npm_racine_et_nested(self):
        packages = {'': {}, 'node_modules/playwright': {'version': '1.61.0'},
                    'node_modules/outil/node_modules/playwright': {'version': '1.61.0'}}
        d.verifier_versions_npm(packages, {'playwright': '1.61.0'})
        for chemin in packages:
            if not chemin:
                continue
            divergent = copy.deepcopy(packages)
            divergent[chemin]['version'] = '1.58.2'
            with self.subTest(chemin=chemin), self.assertRaisesRegex(ValueError, 'socle commun'):
                d.verifier_versions_npm(divergent, {'playwright': '1.61.0'})
