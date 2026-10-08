import importlib.util
import json
from pathlib import Path
import tempfile
import shutil
import subprocess
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('sauvegarde_externe',Path(__file__).resolve().parents[1]/'scripts/sauvegarde-externe.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class SauvegardeExterne(unittest.TestCase):
    @unittest.skipUnless(shutil.which('age') and shutil.which('age-keygen'),'age requis')
    def test_copie_age_reelle_et_echec_atomique_sans_clair(self):
        with tempfile.TemporaryDirectory() as root:
            r=Path(root);source=r/'source';source.mkdir();disque=r/'disque';disque.mkdir()
            cle=r/'cle';mauvaise=r/'autre-cle'
            for cible in (cle,mauvaise):
                subprocess.run(['age-keygen','-o',str(cible)],check=True,stderr=subprocess.DEVNULL)
            recipient=subprocess.check_output(['age-keygen','-y',str(cle)],text=True).strip()
            date='2026-10-08T120000Z'
            for nom in ('vision','mrjam_identite','sessions'):
                contenu=subprocess.check_output(['age','-r',recipient],input=b'contenu-synthetique-confidentiel')
                (source/(nom+'-'+date+'.age')).write_bytes(contenu)
            module.manifeste(source,date);document=source/('mrjam-'+date+'.json')
            with patch.object(module.os.path,'ismount',return_value=True):
                with self.assertRaises(subprocess.CalledProcessError):
                    module.copier(source,document,disque,mauvaise)
                self.assertEqual(list((disque/'mrjam-sauvegardes').iterdir()),[])
                resultat=module.copier(source,document,disque,cle)
                self.assertTrue(resultat['copie_chiffree_verifiee'])
                with self.assertRaisesRegex(ValueError,'déjà copiée'):
                    module.copier(source,document,disque,cle)
            for copie in (disque/'mrjam-sauvegardes'/date).iterdir():
                self.assertEqual(copie.stat().st_mode&0o077,0)
                self.assertNotIn(b'contenu-synthetique-confidentiel',copie.read_bytes())

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
