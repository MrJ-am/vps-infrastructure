"""Real tar over invented files; no live service or production directory."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("snapshot", Path(__file__).with_name("snapshot.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.state = self.base / "state"
        self.state.mkdir(mode=0o700)
        self.backup = self.base / "backup"
        self.backup.mkdir(mode=0o700)
        self.subject = module.FrozenSnapshot(self.state, self.backup, shutil.which("tar"), owner=os.getuid())
        for name in module.REQUIRED:
            root = self.state / name
            root.mkdir(parents=True)
            marker = root / "invented-marker"
            marker.write_text("SYNTHETIC_BASELINE")
            marker.chmod(0o600)

    def tearDown(self):
        self.temporary.cleanup()

    def test_paired_restore_and_retention_of_candidate_and_new_roots(self):
        self.subject.create()
        self.assertEqual(set(self.subject.verify()["roots"]), module.REQUIRED)
        for name in module.REQUIRED:
            (self.state / name / "invented-marker").write_text("SYNTHETIC_CANDIDATE")
        fresh = self.state / "mrjam-vision-cycle"
        fresh.mkdir()
        (fresh / "new-state").write_text("SYNTHETIC_NEW")
        self.subject.restore()
        for name in module.REQUIRED:
            marker = self.state / name / "invented-marker"
            self.assertEqual(marker.read_text(), "SYNTHETIC_BASELINE")
            self.assertEqual(marker.stat().st_mode & 0o777, 0o600)
            self.assertEqual((self.backup / "candidate-state-retained" / name / "invented-marker").read_text(), "SYNTHETIC_CANDIDATE")
        self.assertFalse(fresh.exists())
        self.assertTrue((self.backup / "candidate-state-retained/mrjam-vision-cycle/new-state").exists())

    def test_snapshot_does_not_dereference_nested_links(self):
        external = self.base / "synthetic-outside-selection"
        external.write_text("SYNTHETIC_OUTSIDE")
        link = self.state / "nextcloud" / "link"
        link.symlink_to(external)
        self.subject.create()
        self.subject.restore()
        self.assertTrue(link.is_symlink())
        self.assertEqual(os.readlink(link), str(external))
        self.assertEqual(external.read_text(), "SYNTHETIC_OUTSIDE")

    def test_integrity_failure_prevents_any_state_move(self):
        self.subject.create()
        with self.subject.archive.open("ab") as stream:
            stream.write(b"synthetic-corruption")
        with self.assertRaises(module.SnapshotRefused):
            self.subject.restore()
        self.assertFalse((self.backup / "candidate-state-retained").exists())
        self.assertTrue((self.state / "postgresql/17/invented-marker").exists())

    def test_manifest_cannot_add_a_source_or_repeat_it(self):
        self.subject.create()
        original = self.subject.manifest.read_text()
        for extra in ["../../outside", "forgejo"]:
            value = json.loads(original)
            value["roots"].append(extra)
            self.subject.manifest.write_text(json.dumps(value))
            with self.assertRaises(module.SnapshotRefused):
                self.subject.verify()

    def test_missing_required_source_and_source_symlink_refused(self):
        source = self.state / "kanidm"
        source.rename(self.state / "outside")
        with self.assertRaises(module.SnapshotRefused):
            self.subject.create()
        source.symlink_to(self.state / "outside")
        with self.assertRaises(module.SnapshotRefused):
            self.subject.create()
        self.assertFalse(self.subject.archive.exists())

    def test_snapshot_cannot_overwrite_an_existing_return_point(self):
        self.subject.create()
        digest = module.regular_digest(self.subject.archive)
        with self.assertRaises(module.SnapshotRefused):
            self.subject.create()
        self.assertEqual(module.regular_digest(self.subject.archive), digest)

    def test_manifest_never_contains_application_markers(self):
        self.subject.create()
        self.assertNotIn("SYNTHETIC_BASELINE", self.subject.manifest.read_text())
        self.assertEqual(self.subject.archive.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.subject.manifest.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
