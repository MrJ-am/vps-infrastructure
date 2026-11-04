"""Synthetic databases only; private markers must not escape predicates."""
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("obligations", Path(__file__).with_name("preflight_obligations.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class Predicates(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name, "state.sqlite")
        self.db = sqlite3.connect(self.path)
        self.db.executescript("CREATE TABLE courriels(id TEXT); CREATE TABLE fermetures(sujet TEXT PRIMARY KEY,outils_effaces INTEGER,terminee INTEGER); CREATE TABLE effacements_termines(utilisateur TEXT PRIMARY KEY);")
        self.path.chmod(0o600)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def inspect(self, table="fermetures"):
        return m.inspect_database(str(self.path), table, os.getuid(), os.getgid())

    def test_empty_tables(self):
        self.assertEqual(self.inspect(), {"state":"observed", "marker_table_present":True, "markers_present":False, "incomplete_present":False})

    def test_absent_distinct_from_empty(self):
        self.db.execute("DROP TABLE fermetures")
        self.assertFalse(self.inspect()["marker_table_present"])

    def test_each_pending_state_without_private_values(self):
        for tools in (None, 1700000000):
            self.db.execute("DELETE FROM fermetures")
            self.db.execute("INSERT INTO fermetures VALUES(?,?,NULL)", ("SYNTHETIC_PRIVATE_USER",tools))
            self.db.commit()
            result = self.inspect()
            self.assertTrue(result["incomplete_present"])
            self.assertNotIn("PRIVATE",json.dumps(result))

    def test_complete_and_cycle_presence(self):
        self.db.execute("INSERT INTO fermetures VALUES('invented',1,2)")
        self.db.execute("INSERT INTO effacements_termines VALUES('invented')")
        self.db.commit()
        self.assertTrue(self.inspect()["markers_present"])
        self.assertFalse(self.inspect()["incomplete_present"])
        self.assertTrue(self.inspect("effacements_termines")["markers_present"])

    def test_committed_wal_seen_uncommitted_changes_ignored(self):
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("INSERT INTO fermetures VALUES('invented',1,NULL)")
        self.db.commit()
        self.db.execute("DELETE FROM fermetures")
        self.assertTrue(self.inspect()["incomplete_present"])

    def test_views_and_different_schemas_refused(self):
        self.db.execute("DROP TABLE fermetures")
        self.db.execute("CREATE VIEW fermetures AS SELECT * FROM courriels")
        with self.assertRaises(m.Refused): self.inspect()
        self.db.execute("DROP VIEW fermetures")
        self.db.execute("CREATE TABLE fermetures(sujet TEXT, outils_effaces INTEGER, terminee INTEGER)")
        with self.assertRaises(m.Refused): self.inspect()

    def test_no_database_mutations(self):
        before = self.path.read_bytes()
        self.inspect()
        self.assertEqual(before, self.path.read_bytes())

    def test_symlink_and_permissions_refused(self):
        original = self.path.with_suffix(".original")
        self.path.rename(original)
        self.path.symlink_to(original)
        with self.assertRaises(m.Refused): self.inspect()
        self.path.unlink()
        original.rename(self.path)
        self.path.chmod(0o644)
        with self.assertRaises(m.Refused): self.inspect()

    def test_internal_error_never_exported(self):
        with patch.object(m, "inspect_database", side_effect=RuntimeError("PRIVATE_MARKER")):
            self.assertEqual(m.observe(m.CYCLE,"effacements_termines"),{"state":"unknown"})


if __name__ == "__main__":
    unittest.main()
