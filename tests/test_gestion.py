"""Secret provisoire Keycloak : privé, idempotent, jamais remplacé.

Les entrées métier sont qualifiées par les 644 cas gestion-differentiel et les
parcours SQL/multi-comptes du binaire commun ; aucun ancien daemon importé ici.
"""
import importlib.util
from pathlib import Path
import tempfile
import unittest

def charger(nom,fichier):
    spec=importlib.util.spec_from_file_location(nom,Path(__file__).resolve().parents[1]/fichier)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
identite=charger('identite_preparer','scripts/identite-preparer.py')

class Gestion(unittest.TestCase):
    def test_secret_initial_prive_non_remplace(self):
        with tempfile.TemporaryDirectory() as root:
            modele=Path(__file__).resolve().parents[1]/'operations/identite/realm.json'
            resultat=identite.preparer(modele,root)
            self.assertFalse(resultat['inscriptions']);self.assertFalse(resultat['secret_affiche'])
            secret=Path(root)/'oidc-client.secret';ancien=secret.read_bytes()
            self.assertEqual(secret.stat().st_mode&0o077,0)
            self.assertTrue(identite.preparer(modele,root)['import_existant_verifie'])
            self.assertEqual(secret.read_bytes(),ancien)

if __name__=='__main__':unittest.main()
