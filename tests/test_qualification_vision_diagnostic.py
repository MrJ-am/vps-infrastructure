"""Un échec opérateur reste identifiable sans exposer ses réponses privées."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('preparation_diagnostic', ROOT / 'scripts/vision-multiutilisateur-preparer.py')
MODULE = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(MODULE)


class DiagnosticPrive(unittest.TestCase):
    def setUp(self):
        self.ancien = (MODULE.DIAGNOSTIC, MODULE.ETAPE)
        self.temporaire = tempfile.TemporaryDirectory()
        MODULE.DIAGNOSTIC = Path(self.temporaire.name) / 'diagnostic.log'
        MODULE.ETAPE = 'restauration_isolee'

    def tearDown(self):
        MODULE.DIAGNOSTIC, MODULE.ETAPE = self.ancien
        self.temporaire.cleanup()

    def test_erreur_sous_processus_conservee_hors_sortie_publique(self):
        prive = b'Detail PostgreSQL : contenu personnel synthetique'
        sortie = io.StringIO()
        r = subprocess.CompletedProcess(['psql'], 1, b'', prive)
        with contextlib.redirect_stdout(sortie), contextlib.redirect_stderr(sortie), patch.object(MODULE.subprocess, 'run', return_value=r):
            with self.assertRaisesRegex(MODULE.PreparationRefusee, '^Commande refusée : psql$'):
                MODULE.commande('psql')
        self.assertEqual(sortie.getvalue(), '')
        self.assertIn(prive, MODULE.DIAGNOSTIC.read_bytes())
        self.assertEqual(MODULE.DIAGNOSTIC.stat().st_mode & 0o777, 0o600)

    def test_exception_imprevue_ne_publie_pas_son_message(self):
        prive = 'nom-de-personne-contenu-prive'
        sortie = io.StringIO()
        with patch('sys.argv', ['preparer', 'a' * 40]), patch.object(MODULE, 'preparer', side_effect=ValueError(prive)), contextlib.redirect_stderr(sortie):
            with self.assertRaises(SystemExit) as arret: MODULE.main()
        self.assertEqual(arret.exception.code, 1)
        resultat = json.loads(sortie.getvalue())
        self.assertEqual(resultat['etape'], 'restauration_isolee')
        self.assertFalse(resultat['activation'])
        self.assertNotIn(prive, sortie.getvalue())
        self.assertIn(prive, MODULE.DIAGNOSTIC.read_text())

    def test_lien_symbolique_ne_modifie_pas_un_autre_fichier(self):
        cible = Path(self.temporaire.name) / 'ailleurs'; cible.write_text('conserver')
        MODULE.DIAGNOSTIC.symlink_to(cible)
        with self.assertRaises(OSError): MODULE.diagnostic_prive(b'prive')
        self.assertEqual(cible.read_text(), 'conserver')

    def test_fichier_non_prive_refuse(self):
        MODULE.DIAGNOSTIC.write_text('conserver'); MODULE.DIAGNOSTIC.chmod(0o644)
        with self.assertRaisesRegex(ValueError, 'non privé'): MODULE.diagnostic_prive(b'prive')
        self.assertEqual(MODULE.DIAGNOSTIC.read_text(), 'conserver')

    def test_sortie_etape_limitee_aux_valeurs_fixes(self):
        with self.assertRaises(ValueError): MODULE.etape('titre-personnel')
        sortie = io.StringIO()
        with contextlib.redirect_stdout(sortie): MODULE.etape('releve_acl')
        self.assertEqual(json.loads(sortie.getvalue()), {'etape': 'releve_acl'})

    def test_trace_bornee(self):
        MODULE.diagnostic_prive(b'x' * 1000000)
        self.assertEqual(MODULE.DIAGNOSTIC.stat().st_size, 65536)


if __name__ == '__main__': unittest.main()
