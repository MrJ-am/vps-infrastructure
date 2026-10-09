"""Entrées bornées avant SQL, sans accepter d'identité dans le corps."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

def charger(nom,fichier):
    spec=importlib.util.spec_from_file_location(nom,Path(__file__).resolve().parents[1]/fichier)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
gestion=charger('vision_gestion','services/vision-gestion/server.py')
identite=charger('identite_preparer','scripts/identite-preparer.py')

class Gestion(unittest.TestCase):
    def test_types_et_identites_refuses_avant_sql(self):
        base={'utilisateur':'compte-test','version':1}
        for p in ({**base,'acteur':'admin'},{**base,'email':'vol@example.test'},
                  {**base,'version':True},{**base,'quota_octets':'10000000'},
                  {**base,'actif':'false'},{**base,'limites':{}},{**base,'quota_octets':10**12}):
            with self.assertRaises(ValueError):gestion.verifier('modifier_compte',p)
        gestion.verifier('modifier_compte',{**base,'administrateur':True,'quota_octets':10000000})

    def test_secret_initial_prive_non_remplace(self):
        with tempfile.TemporaryDirectory() as root:
            modele=Path(__file__).resolve().parents[1]/'operations/identite/realm.json'
            resultat=identite.preparer(modele,root)
            self.assertFalse(resultat['inscriptions']);self.assertFalse(resultat['secret_affiche'])
            secret=Path(root)/'oidc-client.secret';ancien=secret.read_bytes()
            self.assertEqual(secret.stat().st_mode&0o077,0)
            with self.assertRaises(ValueError):identite.preparer(modele,root)
            self.assertEqual(secret.read_bytes(),ancien)

if __name__=='__main__':unittest.main()
