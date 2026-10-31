import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from frontend_inputs import application_path, materialize, verify
from prepare import Refused


class FrontendInputsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.source.mkdir()
        (self.source / "index.html").write_bytes(b"<!doctype html><p>synthetic</p>")
        self.lock = self.root / "sources.json"
        self.specification = {
            "files": {"applications/log/index.html": {"root": "infrastructure", "path": "index.html", "sha256": hashlib.sha256((self.source / "index.html").read_bytes()).hexdigest()}},
            "frontends": {"log": {"source_commit": "a" * 40, "style_revision": "b" * 40}},
        }
        self.lock.write_text(json.dumps(self.specification))
        self.output = self.root / "inputs"

    def prepare(self):
        materialize(self.lock, {"infrastructure": self.source}, self.output)
        return hashlib.sha256((self.output / "materialization.json").read_bytes()).hexdigest()

    def test_exact_closed_export(self):
        digest = self.prepare()
        self.assertEqual(verify(self.output, self.lock, digest)["source_files"], 1)

    def test_changed_source_refused_before_destination(self):
        (self.source / "index.html").write_text("modified")
        with self.assertRaisesRegex(Refused, "SOURCE_HASH_MISMATCH"):
            self.prepare()
        self.assertFalse(self.output.exists())

    def test_source_symlink_refused(self):
        (self.source / "index.html").unlink()
        (self.source / "index.html").symlink_to("../sources.json")
        with self.assertRaisesRegex(Refused, "SOURCE_SYMLINK_REFUSED"):
            self.prepare()

    def test_unexpected_output_refused(self):
        digest = self.prepare()
        (self.output / "unexpected.txt").write_text("extra")
        with self.assertRaisesRegex(Refused, "FRONTEND_FILE_SET_MISMATCH"):
            verify(self.output, self.lock, digest)

    def test_changed_lock_refused(self):
        digest = self.prepare()
        self.lock.write_text(self.lock.read_text() + "\n")
        with self.assertRaisesRegex(Refused, "FRONTEND_SOURCE_LOCK_MISMATCH"):
            verify(self.output, self.lock, digest)

    def test_existing_destination_refused(self):
        self.prepare()
        with self.assertRaisesRegex(Refused, "NEW_DESTINATION_REQUIRED"):
            self.prepare()

    def test_source_selection_excludes_build_cache_and_arbitrary_files(self):
        self.assertTrue(application_path("vision", "interface/compiler.py"))
        self.assertTrue(application_path("vision", "docs/openapi.json"))
        self.assertTrue(application_path("audition", "interface-audition/src/Main.elm"))
        for name in ("interface/dist/app.js", "interface/node_modules/elm/index.js", "docs/private.json", "interface/.env", "interface/data/responses.json"):
            self.assertFalse(application_path("vision", name), name)


if __name__ == "__main__":
    unittest.main()
