"""Un changement de pin lit le vrai diff Git, sans invalider la prose comme du code."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import assemblage as a


class Revisions(unittest.TestCase):
    def git(self,cle,*args):
        return subprocess.check_output(['git','-c','user.name=Fixture','-c','user.email=fixture@example.test',*args],
            cwd=self.chemins[cle],stderr=subprocess.DEVNULL,text=True).strip()

    def commit(self,cle):
        self.git(cle,'add','.');self.git(cle,'commit','--quiet','-m','Fixture synthétique')
        return self.git(cle,'rev-parse','HEAD')

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='mrjam-selector-')
        self.addCleanup(self.tmp.cleanup)
        self.chemins={k:Path(self.tmp.name)/k for k in a.DEPOTS}
        self.m=copy.deepcopy(a.manifeste())
        for cle,p in self.chemins.items():
            p.mkdir();self.git(cle,'init','--quiet')
            (p/'README.md').write_text('Fixture de sélection, aucun projet réel.\n')
            revision=self.commit(cle)
            if cle!='vps':self.m['sources'][cle]['revision']=revision
        (self.chemins['vps']/'assemblage').mkdir()
        self.ecrire_manifeste();self.avant=self.commit('vps')

    def ecrire_manifeste(self):
        (self.chemins['vps']/'assemblage/manifest.json').write_text(json.dumps(self.m))

    def mise_a_jour(self,chemin,texte):
        p=self.chemins['vision']/chemin;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(texte)
        self.m['sources']['vision']['revision']=self.commit('vision')
        self.ecrire_manifeste();self.commit('vps')
        return a.selection(a.changements_assemblage(self.avant,self.chemins),a.catalogue())

    def test_pin_de_prose_conserve_les_tests_arithmetiques(self):
        self.assertEqual(['editorial'],self.mise_a_jour('README.md','Nouvelle prose de fixture.\n'))

    def test_pin_macro_json_propage_aux_consommateurs(self):
        selection=self.mise_a_jour('src/json.lisp','(defmacro fixture () nil)\n')
        for nom in ('matheval-pures','vision-contrats','native-contrats'):
            self.assertIn(nom,selection)
        self.assertNotIn('logique-correcteur',selection)

    def test_changement_de_toolchain_elargit(self):
        self.m['toolchain_fixture']='autre compilateur de test'
        self.ecrire_manifeste();self.commit('vps')
        self.assertEqual(sorted(a.catalogue()),a.selection(a.changements_assemblage(self.avant,self.chemins),a.catalogue()))
