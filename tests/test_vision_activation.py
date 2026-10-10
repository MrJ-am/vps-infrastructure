"""Garde de bascule : preuves réelles, marques concurrentes et installation privée."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('activation',ROOT/'scripts/vision-essai-activer.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)


class Activation(unittest.TestCase):
    def test_preparation_exacte_complete_et_sans_mutation(self):
        r=json.loads((ROOT/'operations/vision-essai-preparation-reelle.json').read_text())
        m.verifier_preparation(r,r['infrastructure'])
        for k,v in [('restauration_vision_reelle',False),('association_et_admin_isoles',False),
                ('retour_acl_rejoue',False),('entree_persistante_reproduite',False),
                ('timer_independant_repete',False),('generation_active_modifiee',True),
                ('inscriptions',True),('fichiers_interface',True),('version',True),
                ('vision','a'*40),('infrastructure','a'*40)]:
            d=copy.deepcopy(r);d[k]=v
            with self.subTest(k=k),self.assertRaises(ValueError):m.verifier_preparation(d,r['infrastructure'])

    def test_finalisation_refuse_echec_retour_ou_absence_preuve(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp)
            for n in ('commence','teste'):(d/n).write_text('1\n')
            m.verifier_finalisation(d)
            for n in ('echec','retour-commence','retour-termine','enregistre'):
                (d/n).write_text('1\n')
                with self.subTest(n=n),self.assertRaises(ValueError):m.verifier_finalisation(d)
                (d/n).unlink()
            (d/'teste').unlink()
            with self.assertRaises(ValueError):m.verifier_finalisation(d)

    @unittest.skipUnless(os.geteuid()==0,'Qualification root exécutée en CI')
    def test_installation_ne_suit_pas_de_lien_et_ne_remplace_rien(self):
        with tempfile.TemporaryDirectory(dir='/root') as tmp:
            d=Path(tmp);p=d/'generation/operateur'
            m.installer_prive(p,b'contenu exact',0o700)
            self.assertEqual(p.read_bytes(),b'contenu exact')
            self.assertEqual(stat.S_IMODE(p.stat().st_mode),0o700)
            with self.assertRaises(FileExistsError):m.installer_prive(p,b'etranger')
            autre=d/'etranger';autre.mkdir();lien=d/'lien';lien.symlink_to(autre)
            with self.assertRaises(ValueError):m.installer_prive(lien/'fichier',b'refuse')
            self.assertFalse((autre/'fichier').exists())
            autre.chmod(0o777)
            with self.assertRaises(ValueError):m.installer_prive(autre/'fichier',b'refuse')


if __name__=='__main__':unittest.main()
