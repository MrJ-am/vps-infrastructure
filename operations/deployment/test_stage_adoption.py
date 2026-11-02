"""Real SQLite image tests on invented values, including committed WAL state."""
import importlib.util
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from contextlib import closing
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("stage_adoption", Path(__file__).with_name("stage_adoption.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class StagingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.source = Path(self.tmp.name, "source.sqlite")
        self.destination = Path(self.tmp.name, "image.sqlite")
        self.db = sqlite3.connect(self.source)
        self.db.execute("CREATE TABLE synthetic(id INTEGER PRIMARY KEY, opaque BLOB)")
        self.db.execute("INSERT INTO synthetic VALUES(1,?)", (b"INVENTED_PRIVATE\x00\xff",))
        self.db.commit()
        self.source.chmod(0o600)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def image(self):
        m.image(self.source, self.destination, os.getuid(), os.getgid(), os.getgid(), os.getuid())

    def test_exact_values_readonly_output_and_source_unchanged(self):
        before = self.source.read_bytes()
        self.image()
        with closing(sqlite3.connect(self.destination)) as db:
            self.assertEqual(db.execute("SELECT * FROM synthetic").fetchall(), [(1,b"INVENTED_PRIVATE\x00\xff")])
        self.assertEqual(self.destination.stat().st_mode & 0o777, 0o440)
        self.assertEqual(before, self.source.read_bytes())

    def test_wal_commit_included_uncommitted_change_ignored(self):
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("INSERT INTO synthetic VALUES(2,?)", (b"COMMITTED_WAL",))
        self.db.commit()
        self.db.execute("DELETE FROM synthetic")
        self.image()
        with closing(sqlite3.connect(self.destination)) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM synthetic").fetchone(),(2,))
        self.assertFalse(self.destination.with_name(self.destination.name + "-wal").exists())

    def test_existing_destination_never_overwritten(self):
        self.destination.write_bytes(b"PRESERVE")
        with self.assertRaises(FileExistsError): self.image()
        self.assertEqual(self.destination.read_bytes(), b"PRESERVE")

    def test_source_and_destination_symlinks_refused(self):
        actual = self.source.with_name("actual.sqlite")
        self.source.rename(actual)
        self.source.symlink_to(actual)
        with self.assertRaises(m.Refused): self.image()
        self.source.unlink()
        actual.rename(self.source)
        self.destination.symlink_to("/never-write")
        with self.assertRaises(FileExistsError): self.image()

    def test_permissive_or_wrong_owner_source_refused(self):
        self.source.chmod(0o644)
        with self.assertRaises(m.Refused): self.image()
        self.source.chmod(0o600)
        with self.assertRaises(m.Refused):
            m.image(self.source, self.destination, os.getuid()+1, os.getgid())

    def test_capacity_and_corruption_refused_without_private_diagnostics(self):
        with patch.object(m, "MAXIMUM", 4096):
            with self.assertRaises(m.Refused): self.image()
        self.source.write_bytes(b"INVENTED_PRIVATE_CORRUPTION")
        with self.assertRaises(m.Refused) as caught: self.image()
        self.assertNotIn("PRIVATE",str(caught.exception))


if __name__ == "__main__":
    unittest.main()
