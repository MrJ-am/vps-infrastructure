"""Refuser une activation périmée et une finalisation après retour."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('mcp_deployer',Path(__file__).resolve().parents[1]/'scripts/mcp-deployer.py')
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
    def test_finalisation_refuse_changement_concurrent(self):
        (self.d/'essai.json').write_text('{}')
        with patch.object(m,'etat',return_value={**self.r['avant'],'actif':'nouveau','configuration':'autre'}):
            with self.assertRaisesRegex(RuntimeError,'Changement concurrent'):m.finaliser(self.revision)
        self.execution.assert_not_called()


if __name__=='__main__':unittest.main()
