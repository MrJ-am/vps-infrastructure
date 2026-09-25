"""Refuser une activation périmée et une finalisation après retour."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('mcp_deployer',Path(__file__).resolve().parents[1]/'scripts/vision-identite-deployer.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class GardeFous(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.d=Path(self.tmp.name)
        self.revision='a'*40
        self.r={'avant':{'actif':'ancien','demarrage':'ancien','configuration':'empreinte'},'candidat':'nouveau'}
        (self.d/'preparation.json').write_text(json.dumps(self.r))
        p=patch.object(m,'dossier',return_value=self.d);p.start();self.addCleanup(p.stop)
        p=patch.object(m,'executer');self.execution=p.start();self.addCleanup(p.stop)
    def test_activation_refuse_un_etat_modifie(self):
        with patch.object(m,'etat',return_value={'actif':'autre'}):
            with self.assertRaisesRegex(RuntimeError,'État modifié'):m.demarrer(self.revision)
        self.execution.assert_not_called()
        self.assertFalse((self.d/'engage').exists())
    def test_finalisation_refuse_retour_deja_engage(self):
        (self.d/'essai.json').write_text('{}');(self.d/'retour-engage').touch()
        with self.assertRaisesRegex(RuntimeError,'retour engagé'):m.finaliser(self.revision)
        self.execution.assert_not_called()
    def test_finalisation_exige_essai(self):
        with self.assertRaisesRegex(RuntimeError,'Essai absent'):m.finaliser(self.revision)
        self.execution.assert_not_called()
    def test_retour_tardif_sans_effet(self):
        (self.d/'enregistre').touch()
        with patch.object(m.subprocess,'run') as run:m.retour(self.revision)
        run.assert_not_called();self.execution.assert_not_called()
    def test_ancien_timer_ne_retablit_pas_la_generation_apres_autre_publication(self):
        (self.d/'engage').touch()
        with patch.object(m,'etat',return_value={
                'actif':'nouveau','demarrage':'nouveau','configuration':'nouvelle-publication'}):
            with patch.object(m.subprocess,'run'):
                with self.assertRaisesRegex(RuntimeError,'retour interdit'):
                    m.retour(self.revision)
        self.execution.assert_not_called()
        self.assertFalse((self.d/'retour-engage').exists())
    def test_retour_immediat_annule_le_timer_de_la_revision(self):
        (self.d/'engage').touch()
        (self.d/'configuration-avant.nix').write_text('ancien')
        entree=self.d/'configuration.nix'
        entree.write_text('nouveau')
        with patch.object(m,'etat',return_value=self.r['avant']):
            with patch.object(m.subprocess,'run') as run:
                with patch.object(m,'ENTREE',entree):
                    m.retour(self.revision)
        self.assertTrue((self.d/'retour-engage').exists())
        run.assert_any_call(['systemctl','stop','vision-identite-retour-'+self.revision[:12]+'.timer'],
                            check=False)
    def test_finalisation_refuse_changement_concurrent(self):
        (self.d/'essai.json').write_text('{}')
        with patch.object(m,'etat',return_value={**self.r['avant'],'actif':'nouveau','configuration':'autre'}):
            with self.assertRaisesRegex(RuntimeError,'Changement concurrent'):m.finaliser(self.revision)
        self.execution.assert_not_called()


if __name__=='__main__':unittest.main()
