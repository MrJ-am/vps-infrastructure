"""Real tar over invented files; no live service or production directory."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

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

    def test_interruption_during_quarantine_recovers_without_discarding_candidate_files(self):
        self.subject.create()
        for name in module.REQUIRED:
            (self.state / name / "invented-marker").write_text("SYNTHETIC_CANDIDATE")
        real_rename = os.rename
        count = 0

        def interrupted(source, destination):
            nonlocal count
            count += 1
            if count == 4:
                raise OSError("SYNTHETIC_INTERRUPTION")
            return real_rename(source, destination)

        with patch.object(module.os, "rename", side_effect=interrupted):
            with self.assertRaises(OSError):
                self.subject.restore()
        resumed = module.FrozenSnapshot(self.state, self.backup, shutil.which("tar"), owner=os.getuid())
        resumed.restore()
        retained = list(self.backup.glob("candidate-state-retained*"))
        self.assertEqual(len(retained), 2)
        for name in module.REQUIRED:
            self.assertEqual((self.state / name / "invented-marker").read_text(), "SYNTHETIC_BASELINE")
            copies = [root / name / "invented-marker" for root in retained if (root / name / "invented-marker").exists()]
            self.assertEqual(len(copies), 1)
            self.assertEqual(copies[0].read_text(), "SYNTHETIC_CANDIDATE")

    def test_partial_extraction_is_retained_on_retry_and_original_archive_unchanged(self):
        self.subject.create()
        original_hash = module.regular_digest(self.subject.archive)

        def partial_extract(args, timeout):
            path = self.state / "kanidm"
            path.mkdir()
            (path / "partial-file").write_text("SYNTHETIC_PARTIAL")
            raise module.SnapshotRefused("SNAPSHOT_OPERATION_FAILED")

        with patch.object(self.subject, "command", side_effect=partial_extract):
            with self.assertRaises(module.SnapshotRefused):
                self.subject.restore()
        self.subject.restore()
        self.assertEqual((self.backup / "candidate-state-retained-02/kanidm/partial-file").read_text(), "SYNTHETIC_PARTIAL")
        self.assertFalse((self.state / "kanidm/partial-file").exists())
        self.assertEqual(module.regular_digest(self.subject.archive), original_hash)
        self.assertTrue((self.state / "postgresql/17/invented-marker").exists())

    def test_quarantine_symlink_cannot_be_used_or_skipped_as_a_previous_attempt(self):
        self.subject.create()
        (self.backup / "candidate-state-retained").symlink_to(self.state)
        with self.assertRaises(module.SnapshotRefused):
            self.subject.restore()
        self.assertEqual((self.state / "kanidm/invented-marker").read_text(), "SYNTHETIC_BASELINE")


if __name__ == "__main__":
    unittest.main()
