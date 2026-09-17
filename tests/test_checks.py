import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from registry import load, validate, unique_object
from probe import compare, validate_response


class RegistryChecks(unittest.TestCase):
    def setUp(self):
        self.projects = {"matheval": copy.deepcopy(load()["matheval"])}

    def second(self):
        extra = copy.deepcopy(self.projects["matheval"])
        extra.update(domain="demo.example.com", aliases=[], port=3001)
        self.projects["demo"] = extra
        return extra

    def test_independent_project(self):
        self.second()
        validate(self.projects)

    def test_duplicate_port_rejected(self):
        self.second()["port"] = 3000
        with self.assertRaises(ValueError):
            validate(self.projects)

    def test_alias_cannot_steal_existing_domain(self):
        self.second()["aliases"] = ["principiipetit.io"]
        with self.assertRaises(ValueError):
            validate(self.projects)

    def test_domain_injection_rejected(self):
        self.second()["domain"] = "example.com; return 200"
        with self.assertRaises(ValueError):
            validate(self.projects)

    def test_repeated_json_key_cannot_silently_replace_project(self):
        with self.assertRaises(ValueError):
            json.loads('{"matheval": {}, "matheval": {}}', object_pairs_hook=unique_object)

    def test_pinned_module_matches_provenance(self):
        root = Path(__file__).resolve().parents[1]
        source = json.loads((root / "vendor/matheval/source.json").read_text())
        content = (root / "vendor/matheval/matheval.nix").read_bytes()
        self.assertEqual(hashlib.sha256(content).hexdigest(), source["sha256"])


class HTTPChecks(unittest.TestCase):
    def test_parking_page_is_not_a_healthy_api(self):
        probe = {"status": 200, "contentType": "application/json", "json": {"status": "ok"}}
        with self.assertRaises(ValueError):
            validate_response("https://example.com/api/health", probe, (200, {"Content-Type": "text/html"}, b"parking"))

    def test_wrong_health_payload_rejected(self):
        with self.assertRaises(ValueError):
            validate_response("https://example.com/api/health", {"status": 200, "json": {"status": "ok"}},
                              (200, {"Content-Type": "application/json"}, b'{"status":"error"}'))

    def test_anonymous_admin_must_stay_unauthorized(self):
        with self.assertRaises(ValueError):
            validate_response("https://example.com/admin/me", {"status": 401}, (200, {}, b"{}"))

    def test_new_project_allowed_but_old_checks_must_survive(self):
        compare({"old": {"sha256": "a"}}, {"old": {"sha256": "a"}, "new": {"status": 200}})
        with self.assertRaises(ValueError):
            compare({"old": {"sha256": "a"}}, {"new": {"status": 200}})

    def test_changed_assets_rejected(self):
        with self.assertRaises(ValueError):
            compare({"old": {"sha256": "a"}}, {"old": {"sha256": "b"}})


if __name__ == "__main__":
    unittest.main()
