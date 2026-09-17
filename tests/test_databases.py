import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from databases import load, validate


class DatabaseChecks(unittest.TestCase):
    def test_registered_matheval_preserved(self):
        self.assertEqual(load()["matheval"], {"name": "matheval"})

    def test_vision_example_is_not_active(self):
        example = json.loads((ROOT / "examples/vision-database.json").read_text())
        validate({**load(), **example})
        self.assertNotIn("vision", load())

    def test_another_project_cannot_take_matheval(self):
        with self.assertRaises(ValueError):
            validate({"matheval": {"name": "matheval"}, "vision": {"name": "matheval"}})

    def test_reserved_names_and_sql_hba_injection_rejected(self):
        for name in ("postgres", "root", "template1", "all", "pg_monitor", "a" * 64,
                     'x"; DROP DATABASE matheval;--', "x\nlocal all all trust", "a-b"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate({"example": {"name": name}})

    def test_unknown_settings_cannot_be_silently_ignored(self):
        with self.assertRaises(ValueError):
            validate({"vision": {"name": "vision", "superuser": True}})

    def test_empty_registry_is_valid(self):
        validate({})

    def test_local_patch_recovers_exact_upstream_module(self):
        source = json.loads((ROOT / "vendor/matheval/source.json").read_text())
        with tempfile.TemporaryDirectory() as directory:
            recovered = Path(directory) / "upstream.nix"
            subprocess.run(["patch", "--batch", "--silent", "--reverse", "--output", str(recovered),
                            str(ROOT / "vendor/matheval/matheval.nix"), str(ROOT / source["patch"])], check=True)
            self.assertEqual(hashlib.sha256(recovered.read_bytes()).hexdigest(), source["upstream_sha256"])


if __name__ == "__main__":
    unittest.main()
