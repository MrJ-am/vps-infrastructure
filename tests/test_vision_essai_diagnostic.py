"""Aucun nom d'unité libre, identité, chemin ou journal brut exporté."""
import importlib.util
import json
from pathlib import Path
import unittest

s=importlib.util.spec_from_file_location('essai_diagnostic',Path(__file__).resolve().parents[1]/'scripts/vision-essai-diagnostiquer.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)


class Diagnostic(unittest.TestCase):
    def test_action_concrete_connue_et_triggers(self):
        r=m.classer('would stop the following units: systemd-tmpfiles-resetup.service\nwould activate the configuration')
        self.assertEqual(r['actions_connues'],[dict(action='stop',unite='systemd-tmpfiles-resetup.service')])
        self.assertTrue(r['activation_simulee']);self.assertFalse(r['redemarrage_systemd_annonce'])

    def test_inconnu_et_journal_prive_non_exportes(self):
        r=m.classer('secret@example.test /root/contenu\nwould restart the following units: mot-secret.service, matheval.service')
        self.assertEqual(r['unites_inconnues'],1)
        self.assertEqual(r['actions_connues'],[dict(action='restart',unite='matheval.service')])
        self.assertNotIn('secret',json.dumps(r));self.assertNotIn('/root',json.dumps(r))
