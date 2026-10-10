"""Générateur durable et fermeture sous le verrou commun de finalisation."""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('reprise',ROOT/'scripts/vision-essai-reprise.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


@unittest.skipUnless(os.geteuid()==0,'Qualification root exécutée en CI')
class Reprise(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.r=Path(self.tmp.name)
        self.d=self.r/('a'*40);self.d.mkdir(mode=0o700)
        self.outils=self.r/'outils';self.outils.mkdir()
        for n in ('bash','flock','stat','mktemp','sync','mv','mkdir','cp','ln'):
            (self.outils/n).symlink_to(shutil.which(n))
        p=self.outils/'systemctl';p.write_text('#!/bin/sh\nexit 0\n');p.chmod(0o700)
        self.unites=self.r/'unites';self.unites.mkdir()
        self.recette=m.fichiers(self.d,self.outils,'vision-essai-retour-'+self.d.name[:12],unites=self.unites)
        for nom,contenu in self.recette.items():(self.d/nom).write_text(contenu)
        self.sorties=[self.r/n for n in ('normal','avant','apres')]
        for p in self.sorties:p.mkdir()
    def tearDown(self):self.tmp.cleanup()
    def executer(self,nom,args=()):
        return subprocess.run(['bash',str(self.d/nom),*map(str,args)],capture_output=True,timeout=10)

    def test_generateur_apres_redemarrage_reconstitue_unite_et_lien(self):
        self.assertEqual(self.executer('reprise-generateur.sh',self.sorties).returncode,0)
        self.assertEqual(list(self.sorties[0].iterdir()),[])
        (self.d/'commence').write_text('1\n')
        self.assertEqual(self.executer('reprise-generateur.sh',self.sorties).returncode,0)
        nom='vision-essai-retour-'+self.d.name[:12]+'.service'
        self.assertEqual((self.sorties[0]/nom).read_text(),self.recette['reprise.service'])
        self.assertEqual((self.sorties[0]/'multi-user.target.wants'/nom).resolve(),self.sorties[0]/nom)
        self.assertIn('Type=exec',self.recette['reprise.service'])
        self.assertIn('OnActiveSec=15min',self.recette['reprise.timer'])

    def test_marques_terminales_ne_republient_aucune_unite(self):
        (self.d/'commence').write_text('1\n')
        for marque in ('enregistre','retour-termine'):
            with self.subTest(marque=marque):
                (self.d/marque).write_text('1\n')
                self.assertEqual(self.executer('reprise-generateur.sh',self.sorties).returncode,0)
                self.assertEqual(list(self.sorties[0].iterdir()),[])
                (self.d/marque).unlink()

    def test_fermeture_marque_le_retour_avant_conditions(self):
        self.assertEqual(self.executer('reprise-fermer.sh').returncode,0)
        self.assertEqual((self.d/'retour-commence').read_text(),'1\n')
        for u in m.CLIENTS:
            p=self.unites/(u+'.d')/('90-vision-retour-'+self.d.name[:12]+'.conf')
            self.assertEqual(p.read_text(),'[Unit]\nConditionPathExists=!/\n')

    def test_finalisation_gagne_le_verrou_sans_condition_residuelle(self):
        (self.d/'enregistre').write_text('1\n')
        self.assertEqual(self.executer('reprise-fermer.sh').returncode,0)
        self.assertFalse((self.d/'retour-commence').exists())
        self.assertEqual(list(self.unites.iterdir()),[])

    def test_liens_etrangers_et_clients_non_systeme_refuses(self):
        (self.unites/'vision.service.d').symlink_to(self.r/'etranger')
        self.assertNotEqual(self.executer('reprise-fermer.sh').returncode,0)
        self.assertTrue((self.d/'retour-commence').exists())
        with self.assertRaises(ValueError):m.fichiers(self.d,self.outils,'vision-essai-retour-aaaaaaaaaaaa',clients=['x@personne.service'])
        with self.assertRaises(ValueError):m.fichiers(self.d,self.outils,'autre.service')


if __name__=='__main__':unittest.main()
