import copy
import hashlib
import json
import unittest

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from registry import load, validate


class RegistryChecks(unittest.TestCase):
    def setUp(self):
        self.projects = load()

    def test_vision_contract_is_protected(self):
        vision = self.projects["vision"]
        self.assertEqual(vision["domain"], "vision.mrj.am")
        self.assertEqual(vision["port"], 3001)
        self.assertEqual(vision["maxBodySize"], "64k")
        self.assertEqual(vision["auth"], {
            "prefix": "/api/",
            "basicUserFile": "/var/lib/vision/auth/htpasswd",
            "realm": "Vision API",
        })
        self.assertEqual(vision["privateHealthPath"], "/healthz")
        self.assertIn({
            "path": "/mcp",
            "status": 401,
            "contentType": "application/json",
            "json": {"error": "authentication_required"},
        }, vision["probes"])

    def test_authentication_and_private_health_are_atomic(self):
        for removed in ("auth", "privateHealthPath"):
            projects = copy.deepcopy(self.projects)
            del projects["vision"][removed]
            with self.subTest(removed=removed), self.assertRaises(ValueError):
                validate(projects)

    def test_nginx_injections_are_rejected(self):
        mutations = [
            ("realm", "Vision\nreturn 200"),
            ("realm", 'Vision"; return 200; #'),
            ("basicUserFile", "/etc/passwd"),
            ("basicUserFile", "/var/lib/vision/../secrets"),
            ("prefix", "/api//"),
        ]
        for field, value in mutations:
            projects = copy.deepcopy(self.projects)
            projects["vision"]["auth"][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                validate(projects)

    def test_private_health_cannot_be_publicly_probed(self):
        projects = copy.deepcopy(self.projects)
        projects["vision"]["probes"].append({"path": "/healthz", "status": 200})
        with self.assertRaises(ValueError):
            validate(projects)

    def test_vision_module_matches_reviewed_upstream(self):
        source = json.loads((ROOT / "vendor/vision/source.json").read_text())
        module = (ROOT / "vendor/vision/vision.nix").read_bytes()
        self.assertEqual(source["commit"], "445f9d7e6944d621de33283ca960d772813f47a2")
        self.assertEqual(hashlib.sha256(module).hexdigest(), source["sha256"])


if __name__ == "__main__":
    unittest.main()
