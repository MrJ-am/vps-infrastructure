"""Refus de bundle altéré, lien et provenance incohérente, sans accès VPS."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('preparer',ROOT/'scripts/monolithe-preparer.py')
preparer=importlib.util.module_from_spec(spec);spec.loader.exec_module(preparer)


class BundleTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        (self.root/'document').write_text('Source synthétique, aucune donnée réelle.')
        self.sha=hashlib.sha256((self.root/'document').read_bytes()).hexdigest()
        self.cert={'format':1,'activation':False,'revision':'a'*40,
            'manifest':{'toolchain':{'production':{'nixpkgs':preparer.NIXPKGS}}},
            'fichiers':{'document':self.sha},'qualification':{
             'source_revision':'a'*40,'sorties_nix':{'metier':'/nix/store/'+'a'*32+'-mrjam-metier-'+'a'*12},
             'artefact_sha256':'b'*64}}

    def verifier(self):
        (self.root/'stage.json').write_text(json.dumps(self.cert))
        original=preparer.sha
        def sha(p):
            return 'b'*64 if str(p).startswith('/nix/store/') else original(p)
        with patch.object(preparer,'sha',side_effect=sha):return preparer.verifier_bundle(self.root)

    def test_bundle_exact(self):self.assertEqual(self.verifier()['revision'],'a'*40)

    def test_document_modifie(self):
        (self.root/'document').write_text('Altération')
        with self.assertRaisesRegex(ValueError,'Empreintes'):self.verifier()

    def test_fichier_supplementaire(self):
        (self.root/'inattendu').write_bytes(b'extra')
        with self.assertRaisesRegex(ValueError,'Empreintes'):self.verifier()

    def test_lien(self):
        (self.root/'lien').symlink_to('document')
        with self.assertRaisesRegex(ValueError,'régulier'):self.verifier()

    def test_toolchain_ou_binaire_different(self):
        self.cert['manifest']['toolchain']['production']['nixpkgs']='/nixpkgs/inconnu'
        with self.assertRaisesRegex(ValueError,'Toolchain'):self.verifier()
        self.cert['manifest']['toolchain']['production']['nixpkgs']=preparer.NIXPKGS
        self.cert['qualification']['artefact_sha256']='c'*64
        with self.assertRaisesRegex(ValueError,'Binaire'):self.verifier()

    def test_store_ou_revision_incoherent(self):
        self.cert['qualification']['sorties_nix']['metier']='/tmp/faux-artefact'
        with self.assertRaisesRegex(ValueError,'Paquet'):self.verifier()
        self.cert['qualification']['sorties_nix']['metier']='/nix/store/'+'a'*32+'-mrjam-metier-'+'a'*12
        self.cert['qualification']['source_revision']='d'*40
        with self.assertRaisesRegex(ValueError,'Révision'):self.verifier()


if __name__=='__main__':unittest.main()
