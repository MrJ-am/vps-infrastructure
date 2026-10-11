"""Refus de provenance et des adaptations d'outillage hors inventaire."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
spec=importlib.util.spec_from_file_location('deps',ROOT/'scripts/verifier-dependances.py')
d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)


class Provenance(unittest.TestCase):
    def setUp(self):
        self.lock=json.loads((ROOT/'assemblage/outils/mcp.lock.json').read_text())
        self.inventory=json.loads((ROOT/'assemblage/dependances.json').read_text())

    def verifier(self,lock):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'assemblage/outils').mkdir(parents=True)
            (root/'assemblage/manifest.json').write_bytes((ROOT/'assemblage/manifest.json').read_bytes())
            (root/'assemblage/outils/mcp.lock.json').write_text(json.dumps(lock))
            for p in self.lock['adaptations']:
                dest=root/p['fichier'];dest.parent.mkdir(parents=True,exist_ok=True)
                dest.write_bytes((ROOT/p['fichier']).read_bytes())
            d.verifier_outils_mcp(root,self.inventory)

    def test_inventaire_audite_accepte(self):self.verifier(self.lock)

    def test_source_deplacee_ou_revision_flottante_refusee(self):
        for field,value in [('depot','tiers/autre'),('revision','main'),('url','https://github.com/tiers/main')]:
            with self.subTest(field=field):
                lock=copy.deepcopy(self.lock);lock['outils'][0][field]=value
                with self.assertRaises(ValueError):self.verifier(lock)

    def test_transitive_non_inventoriee_refusee(self):
        lock=copy.deepcopy(self.lock);lock['bibliotheques'][0]['deps'].append('cl-harness')
        with self.assertRaises(ValueError):self.verifier(lock)

    def test_patch_change_non_audite_refuse(self):
        lock=copy.deepcopy(self.lock);lock['adaptations'][0]['sha256']='0'*64
        with self.assertRaises(ValueError):self.verifier(lock)

    def test_cache_toolchain_differente_refuse(self):
        lock=copy.deepcopy(self.lock);lock['sbcl']='2.5.0'
        with self.assertRaises(ValueError):self.verifier(lock)
