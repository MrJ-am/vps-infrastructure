"""Refus des sources non auditées et des outils MCP dans le graphe produit OIDC."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
spec = importlib.util.spec_from_file_location('dependances', ROOT / 'scripts/verifier-dependances.py')
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)


class OIDCProvenance(unittest.TestCase):
    def setUp(self):
        self.lock = json.loads((ROOT / 'assemblage/oidc/dependances.lock.json').read_text())
        self.inventory = json.loads((ROOT / 'assemblage/dependances.json').read_text())

    def verifier(self, lock, hash_valide=True):
        with tempfile.TemporaryDirectory() as dossier:
            root = Path(dossier)
            (root / 'assemblage/oidc').mkdir(parents=True)
            (root / 'assemblage/outils').mkdir()
            (root / 'assemblage/manifest.json').write_bytes((ROOT / 'assemblage/manifest.json').read_bytes())
            (root / 'assemblage/outils/mcp.lock.json').write_bytes((ROOT / 'assemblage/outils/mcp.lock.json').read_bytes())
            raw = json.dumps(lock).encode()
            (root / 'assemblage/oidc/dependances.lock.json').write_bytes(raw)
            inventory = copy.deepcopy(self.inventory)
            if hash_valide:
                inventory['bibliotheques_lisp_oidc']['sha256'] = hashlib.sha256(raw).hexdigest()
            return d.verifier_lisp_oidc(root, inventory)

    def test_graphe_audite_accepte(self):
        self.assertIn('ironclad/public-key/secp256r1', self.verifier(self.lock))
        self.assertNotIn('ironclad', self.verifier(self.lock))

    def test_integrite_lock_obligatoire(self):
        with self.assertRaises(ValueError):
            self.verifier(self.lock, hash_valide=False)

    def test_toolchain_differente_refusee(self):
        lock = copy.deepcopy(self.lock)
        lock['sbcl'] = '2.5.0'
        with self.assertRaises(ValueError):
            self.verifier(lock)

    def test_tool_developpement_ou_transitive_inattendue_refuse(self):
        for nom in ('cl-mcp', 'cl-tron-mcp', 'swank', 'cl-harness'):
            with self.subTest(nom=nom):
                lock = copy.deepcopy(self.lock)
                lock['bibliotheques'][0]['deps'].append(nom)
                with self.assertRaises(ValueError):
                    self.verifier(lock)

    def test_ironclad_autre_source_ou_collection_complete_refuse(self):
        for field, value in [('revision', 'main'), ('hash', '0' * 52),
                             ('systemes', ['ironclad']), ('version', 'latest')]:
            with self.subTest(field=field):
                lock = copy.deepcopy(self.lock)
                next(b for b in lock['bibliotheques'] if b['name'] == 'ironclad')[field] = value
                with self.assertRaises(ValueError):
                    self.verifier(lock)

    def test_source_commune_changee_refusee(self):
        lock = copy.deepcopy(self.lock)
        next(b for b in lock['bibliotheques'] if b['name'] == 'cl-base64')['hash'] = '0' * 52
        with self.assertRaises(ValueError):
            self.verifier(lock)
