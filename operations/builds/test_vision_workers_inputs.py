import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import prepare_vision_workers as workers
from prepare import Refused


class WorkerInputs(unittest.TestCase):
    def fixture(self, root):
        source = root / "source"
        source.mkdir()
        files = {"source/Cargo.lock": b'version = 4\n[[package]]\nname = "invented"\nversion = "0.1.0"\n',
                 "source/src/lib.rs": b"pub fn invented() {}\n",
                 "source/tests/manifest.json": b'{"synthetic":true}\n'}
        blobs = {}
        for name, data in files.items():
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            blobs[name] = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        manifest = {"schema_version":1, "source_commit":"1" * 40, "source_tree":"2" * 40,
                    "source_blobs":blobs, "files":{p:hashlib.sha256(v).hexdigest() for p,v in files.items()}, "cargo_packages":[]}
        raw = json.dumps(manifest).encode()
        (root / "manifest.json").write_bytes(raw)
        return hashlib.sha256(raw).hexdigest()

    def test_complete_public_fixture_and_nested_manifest_are_verified(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            digest = self.fixture(root)
            self.assertEqual(workers.verify(root, digest)["source_commit"], "1" * 40)

    def test_changed_source_is_refused_without_repairing_hash(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            digest = self.fixture(root)
            before = (root / "manifest.json").read_bytes()
            (root / "source/src/lib.rs").write_bytes(b"pub fn changed() {}\n")
            with self.assertRaisesRegex(Refused, "SOURCE_HASH_MISMATCH"):
                workers.verify(root, digest)
            self.assertEqual((root / "manifest.json").read_bytes(), before)

    def test_extra_file_symlink_and_manifest_change_are_refused(self):
        for variant in ("extra", "link", "manifest"):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as name:
                root = Path(name)
                digest = self.fixture(root)
                if variant == "extra":
                    (root / "extra.rs").write_bytes(b"invented")
                elif variant == "link":
                    (root / "source/src/lib.rs").unlink()
                    (root / "source/src/lib.rs").symlink_to("../Cargo.lock")
                else:
                    (root / "manifest.json").write_bytes(b"{}")
                with self.assertRaises(Refused):
                    workers.verify(root, digest)

    def test_removed_source_is_refused(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            digest = self.fixture(root)
            (root / "source/tests/manifest.json").unlink()
            with self.assertRaisesRegex(Refused, "WORKER_INPUT_SET_CHANGED"):
                workers.verify(root, digest)


if __name__ == "__main__":
    unittest.main()
