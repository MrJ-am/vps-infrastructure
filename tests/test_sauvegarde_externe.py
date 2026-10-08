import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('sauvegarde_externe',Path(__file__).resolve().parents[1]/'scripts/sauvegarde-externe.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class SauvegardeExterne(unittest.TestCase):
    def test_manifeste_coherent_modification_et_traversee_refusees(self):
        with tempfile.TemporaryDirectory() as root:
            r=Path(root);date='2026-10-08T120000Z'
            for nom in ('vision','mrjam_identite','sessions'):(r/(nom+'-'+date+'.age')).write_bytes(b'contenu-chiffre-synthetique')
            valeur=module.manifeste(r,date);document=r/('mrjam-'+date+'.json')
            self.assertEqual(module.verifier(r,document),valeur)
            with self.assertRaises(ValueError):module.copier(r,document,r,r/'cle')
            (r/('vision-'+date+'.age')).write_bytes(b'modifie')
            with self.assertRaises(ValueError):module.verifier(r,document)
            valeur['fichiers']={'../secret.age':'a'*64,'vision.age':'a'*64,'sessions.age':'a'*64}
            document.write_text(json.dumps(valeur))
            with self.assertRaises(ValueError):module.verifier(r,document)


if __name__=='__main__':unittest.main()
