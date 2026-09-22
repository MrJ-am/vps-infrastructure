import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

RACINE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(RACINE/'scripts'))
from corrections_artefacts import lire,verifier


class ArtefactsCoordonnes(unittest.TestCase):
    def test_deux_sites_verifies_et_style_commun(self):
        if not (RACINE/'operations/corrections-artefacts.json').exists():
            self.skipTest('Les artefacts ne sont pas encore consignés dans cet atelier')
        self.assertEqual(set(verifier(RACINE)),{'logique','vision'})

    def test_traversee_et_liens_refuses_avant_extraction(self):
        for nom in ('../intrus','dist/../../intrus','/absolu','dist/./ambigu'):
            with self.subTest(nom=nom),tempfile.TemporaryDirectory() as repertoire:
                source=Path(repertoire);p=source/'vendor/candidats/logique.zip';p.parent.mkdir(parents=True)
                with zipfile.ZipFile(p,'w') as z:z.writestr(nom,b'intrus')
                with self.assertRaisesRegex(ValueError,'Entrée ZIP invalide'):
                    lire(source,'logique',{'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})

    def test_empreinte_archive_obligatoire(self):
        with tempfile.TemporaryDirectory() as repertoire:
            source=Path(repertoire);p=source/'vendor/candidats/vision.zip';p.parent.mkdir(parents=True);p.write_bytes(b'archive substituee')
            with self.assertRaisesRegex(ValueError,'Archive différente'):
                lire(source,'vision',{'sha256':'0'*64})

    def test_retour_refuse_une_generation_etrangere(self):
        from unittest.mock import patch
        specification=importlib.util.spec_from_file_location('corrections_sites',RACINE/'scripts/corrections-sites.py')
        m=importlib.util.module_from_spec(specification);specification.loader.exec_module(m)
        with tempfile.TemporaryDirectory() as repertoire:
            d=Path(repertoire);(d/'demarrage-engage').touch()
            r={'avant':{'actif':'ancienne'},'preparation':{'candidats':{'acme':{'systeme':'acme'},'https':{'systeme':'https'}}}}
            with patch.object(m,'lire',return_value=(d,r)),patch.object(m,'etat',return_value={'actif':'autre'}),patch.object(m.subprocess,'run'),patch.object(m,'lien') as lien:
                with self.assertRaisesRegex(ValueError,'autre génération'):m.retour('a'*40)
                lien.assert_not_called()


if __name__=='__main__':unittest.main()
