"""Contrôles des garde-fous : écritures concurrentes et finalisation tardive."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('activation', Path(__file__).resolve().parents[1]/'scripts/migration-activate.py')
activation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(activation)


class MigrationGuards(unittest.TestCase):
    def test_concurrent_inserts_are_preserved_but_deletion_is_rejected(self):
        before = {'answers': ['a', 'a', 'b'], 'migrations': ['v1']}
        self.assertTrue(activation.rows_preserved(before, {'answers': ['c', 'a', 'b', 'a'], 'migrations': ['v1']}))
        self.assertFalse(activation.rows_preserved(before, {'answers': ['a', 'b', 'c'], 'migrations': ['v1']}))
        self.assertFalse(activation.rows_preserved(before, {'answers': ['a', 'a', 'b']}))

    def test_late_completion_cannot_cancel_a_started_rollback(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            self.assertFalse(activation.commit_allowed(state))
            (state/'tested').touch()
            self.assertTrue(activation.commit_allowed(state))
            for marker in ['rollback-started', 'rolled-back', 'worker-failed', 'committed']:
                (state/marker).touch()
                self.assertFalse(activation.commit_allowed(state))
                (state/marker).unlink()
