"""Refus de bundle altéré, lien et provenance incohérente, sans accès VPS."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import assemblage
spec=importlib.util.spec_from_file_location('preparer',ROOT/'scripts/monolithe-preparer.py')
preparer=importlib.util.module_from_spec(spec);spec.loader.exec_module(preparer)


class BundleTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        (self.root/'document').write_text('Source synthétique, aucune donnée réelle.')
        self.sha=hashlib.sha256((self.root/'document').read_bytes()).hexdigest()
        self.suite={'entrees':{'vps':['document']}}
        self.receipt={'format':1,'confiance':'locale-non-attestee','autorise_publication':False,
                      'resultat':'succes','codes':[0],'identite':{
                       'definition':hashlib.sha256(json.dumps(self.suite,sort_keys=True).encode()).hexdigest(),
                       'entrees':{'vps/document':self.sha}}}
        self.cert={'format':2,'activation':False,'revision':'c'*40,'revision_construction':'a'*40,
            'origine_preuves':'codex-local-non-attestee',
            'manifest':{'sources':{'vps':{}},'toolchain':{'production':{'nixpkgs':preparer.NIXPKGS}}},
            'fichiers':{},'recus_locaux_sha256':{},'qualification':{
             'source_revision':'a'*40,'sorties_nix':{'metier':'/nix/store/'+'a'*32+'-mrjam-metier-'+'a'*12},
             'artefact_sha256':'b'*64,'sources_lisp_sha256':{'vps/document':self.sha}}}
        (self.root/'vps/assemblage').mkdir(parents=True)
        (self.root/'vps/document').write_bytes((self.root/'document').read_bytes())
        (self.root/'recus').mkdir()
        self.actualiser()

    def actualiser(self):
        (self.root/'vps/assemblage/manifest.json').write_text(json.dumps(self.cert['manifest']))
        p=self.root/'recus/fixture.json';p.write_text(json.dumps(self.receipt))
        self.cert['recus_locaux_sha256']={'fixture':preparer.sha(p)}
        self.cert['fichiers']={str(p.relative_to(self.root)):preparer.sha(p)
                               for p in self.root.rglob('*') if p.is_file() and p.name!='stage.json'}

    def verifier(self):
        (self.root/'stage.json').write_text(json.dumps(self.cert))
        original=preparer.sha
        def sha(p):
            return 'b'*64 if str(p).startswith('/nix/store/') else original(p)
        with patch.object(preparer,'sha',side_effect=sha), patch.object(assemblage,'catalogue',return_value={'fixture':self.suite}), patch.object(assemblage,'compilation_entrees',return_value={'vps/document':self.sha}):
            return preparer.verifier_bundle(self.root)

    def test_bundle_exact_operateurs_sans_reconstruction(self):self.assertEqual(self.verifier()['revision'],'c'*40)

    def test_graphe_incompatible(self):
        self.cert['qualification']['sources_lisp_sha256']={}
        with self.assertRaisesRegex(ValueError,'Graphe'):self.verifier()

    def test_preuve_non_attestee_ne_devient_pas_ci(self):
        self.receipt['autorise_publication']=True;self.actualiser()
        with self.assertRaisesRegex(ValueError,'Reçu'):self.verifier()

    def test_test_echec_ou_manquant(self):
        self.receipt['codes']=[1];self.actualiser()
        with self.assertRaisesRegex(ValueError,'Reçu'):self.verifier()
        self.receipt['codes']=[0];self.actualiser();self.cert['recus_locaux_sha256']={}
        with self.assertRaisesRegex(ValueError,'Catalogue'):self.verifier()

    def test_definition_ou_entrees_alterees(self):
        self.receipt['identite']['definition']='a'*64;self.actualiser()
        with self.assertRaisesRegex(ValueError,'Entrées'):self.verifier()
        self.receipt['identite']['definition']=hashlib.sha256(json.dumps(self.suite,sort_keys=True).encode()).hexdigest()
        self.receipt['identite']['entrees']={};self.actualiser()
        with self.assertRaisesRegex(ValueError,'Entrées'):self.verifier()

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
