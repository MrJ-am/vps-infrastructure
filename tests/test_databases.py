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
    def test_registered_projects_are_preserved(self):
        self.assertEqual(load(), {
            "matheval": {"name": "matheval"},
            "vision": {"name": "vision"},
            "nextcloud": {"name": "nextcloud"},
        })

    def test_vision_example_matches_active_reservation(self):
        example = json.loads((ROOT / "examples/vision-database.json").read_text())
        self.assertEqual(example["vision"], load()["vision"])

    def test_another_project_cannot_take_registered_names(self):
        for database in ("matheval", "vision", "nextcloud"):
            with self.subTest(database=database), self.assertRaises(ValueError):
                validate({**load(), "other": {"name": database}})

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
        source = json.loads((ROOT / "coordination/archive/matheval-deploiement-20261011/source.json").read_text())
        adaptation = source.get("historical_adaptation", source)
        self.assertEqual(source["sha256"], adaptation["sha256"])
        with tempfile.TemporaryDirectory() as directory:
            recovered = Path(directory) / "upstream.nix"
            subprocess.run(["patch", "--batch", "--silent", "--reverse", "--output", str(recovered),
                            str(ROOT / "coordination/archive/matheval-deploiement-20261011/matheval.nix"), str(ROOT / adaptation["patch"])], check=True)
            self.assertEqual(hashlib.sha256(recovered.read_bytes()).hexdigest(), adaptation["upstream_sha256"])


if __name__ == "__main__":
    unittest.main()
