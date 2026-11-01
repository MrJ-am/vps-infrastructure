"""Tampering with a reviewed source/dependency bundle must refuse the build."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from verify_inputs import file_inventory, verify


class InputBoundary(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "inputs"
        (self.root / "source").mkdir(parents=True)
        (self.root / "node_modules/.bin").mkdir(parents=True)
        self.code = self.root / "source/fixture.rs"
        self.code.write_text("synthetic build source\n")
        self.dep = self.root / "node_modules/tool.js"
        self.dep.write_text("synthetic dependency\n")
        (self.root / "node_modules/.bin/tool").symlink_to("../tool.js")
        self.lock = self.base / "source-lock.json"
        self.lock.write_text(json.dumps({"revision": "synthetic", "repository": "synthetic",
            "files": {"fixture.rs": {"sha256": hashlib.sha256(self.code.read_bytes()).hexdigest()}}}))
        manifest = {"revision": "synthetic", "repository": "synthetic",
                    "source_selection_sha256": hashlib.sha256(self.lock.read_bytes()).hexdigest(),
                    "npm_lifecycle_scripts": False, "files": file_inventory(self.root)}
        self.manifest = self.root / "materialization.json"
        self.manifest.write_text(json.dumps(manifest))
        self.expected = hashlib.sha256(self.manifest.read_bytes()).hexdigest()

    def check(self):
        return verify(self.root, self.expected, self.lock)

    def test_exact_bundle_and_relative_tool_link(self):
        self.assertTrue(self.check())

    def test_changed_source_and_dependency_refused(self):
        for path in (self.code, self.dep):
            with self.subTest(path=path.name):
                original = path.read_bytes()
                path.write_bytes(b"altered\n")
                with self.assertRaises(ValueError):
                    self.check()
                path.write_bytes(original)

    def test_extra_file_refused(self):
        (self.root / "source/unreviewed.rs").write_text("extra")
        with self.assertRaises(ValueError):
            self.check()

    def test_missing_file_refused(self):
        self.code.unlink()
        with self.assertRaises(ValueError):
            self.check()

    def test_manifest_rehash_is_not_authority(self):
        self.manifest.write_text('{"files": {}}')
        with self.assertRaisesRegex(ValueError, "MANIFEST_HASH_MISMATCH"):
            self.check()

    def test_source_lock_substitution_refused(self):
        self.lock.write_text("{}")
        with self.assertRaisesRegex(ValueError, "SOURCE_SELECTION_MISMATCH"):
            self.check()

    def test_escape_link_and_fifo_refused(self):
        outside = self.base / "outside"
        outside.write_text("synthetic outside")
        link = self.root / "source/escape"
        link.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "INPUT_LINK_ESCAPES_ROOT"):
            self.check()
        link.unlink()
        os.mkfifo(link)
        with self.assertRaisesRegex(ValueError, "INPUT_SPECIAL_FILE"):
            self.check()

    def test_executable_mode_change_refused(self):
        self.dep.chmod(0o755)
        with self.assertRaises(ValueError):
            self.check()


if __name__ == "__main__":
    unittest.main()
