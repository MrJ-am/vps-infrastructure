"""Les en-têtes de quota instrumentent une copie, jamais les tests canoniques."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
spec=importlib.util.spec_from_file_location('navigateur',ROOT/'tests/matheval-navigateur.py')
navigateur=importlib.util.module_from_spec(spec);spec.loader.exec_module(navigateur)


class Harnais(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        tests=self.root/'docs/tests/e2e';tests.mkdir(parents=True)
        self.original=b"const {test}=require('@playwright/test');\ntest('synthetique',()=>{});\n"
        (tests/'survey.spec.js').write_bytes(self.original)
        (tests/'gestures.cjs').write_text('module.exports={};\n')
        self.destination=self.root/'docs/.central-tests-synthetique'

    def test_sources_intactes_et_instrumentation_unique(self):
        copie=navigateur.copier_tests(self.root,self.destination)
        self.assertEqual((self.root/'docs/tests/e2e/survey.spec.js').read_bytes(),self.original)
        produit=(copie/'survey.spec.js').read_text()
        self.assertTrue(produit.endswith(self.original.decode()))
        self.assertEqual(produit.count('centralQuotaTest.beforeEach'),1)
        self.assertEqual((copie/'gestures.cjs').read_bytes(),(self.root/'docs/tests/e2e/gestures.cjs').read_bytes())

    def test_chemins_site_et_imports_sont_identiques(self):
        copie=navigateur.copier_tests(self.root,self.destination)
        self.assertEqual((copie/'../../site/data/bank.json').resolve(),self.root/'docs/site/data/bank.json')
        self.assertEqual((copie/'../..').resolve(),self.root/'docs')

    def test_destination_existante_refusee_sans_destruction(self):
        navigateur.copier_tests(self.root,self.destination)
        p=self.destination/'e2e/survey.spec.js';avant=p.read_bytes()
        with self.assertRaises(FileExistsError):navigateur.copier_tests(self.root,self.destination)
        self.assertEqual(p.read_bytes(),avant)


if __name__=='__main__':unittest.main()
