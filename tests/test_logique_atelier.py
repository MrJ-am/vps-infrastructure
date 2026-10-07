"""Contrats du publicateur statique : préserver les autres applications et les releases."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import logique_atelier as publication


class AtelierStatique(unittest.TestCase):
    def test_bascule_bornee(self):
        avant={'systeme':'systeme','demarrage':'systeme','configuration':'empreinte',
               'vision':'vision','vision-interface':'interface','matheval':'memoire','logique':'ancienne'}
        self.assertEqual(publication.attendu({'avant':avant,'publication':'nouvelle'}),{**avant,'logique':'nouvelle'})
        self.assertEqual(avant['logique'],'ancienne')

    def test_liens_atomiques_et_ancienne_release_conservee(self):
        with tempfile.TemporaryDirectory() as dossier:
            racine=Path(dossier);ancienne=racine/'ancienne';nouvelle=racine/'nouvelle'
            ancienne.mkdir();nouvelle.mkdir();(ancienne/'preuve').write_text('conserver')
            lien=racine/'current';lien.symlink_to(ancienne)
            publication.lien(nouvelle,lien)
            self.assertEqual(lien.resolve(),nouvelle)
            self.assertEqual((ancienne/'preuve').read_text(),'conserver')
            publication.lien(ancienne,lien)
            self.assertEqual(lien.resolve(),ancienne)
            self.assertTrue(nouvelle.exists())

    def test_liens_dans_artefact_refuses(self):
        with tempfile.TemporaryDirectory() as dossier:
            racine=Path(dossier);(racine/'fuite').symlink_to('/etc/passwd')
            with self.assertRaises(ValueError):publication.inventaire(racine)

    def test_revision_non_figee_refusee(self):
        for revision in ('main','1234567','../x'):
            with self.assertRaises(ValueError):publication.dossier(revision)

    def test_modification_artefact_detectee(self):
        with tempfile.TemporaryDirectory() as dossier:
            racine=Path(dossier);fichier=racine/'app.js';fichier.write_text('original')
            preparation={'publication':dossier,'fichiers':publication.inventaire(racine)}
            publication.controler_fichiers(preparation)
            fichier.write_text('alteration')
            with self.assertRaises(ValueError):publication.controler_fichiers(preparation)
