import copy
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("register_runner", Path(__file__).parents[1] / "register_runner.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Fixture:
    def __init__(self):
        self.rules = "a" * 40
        self.calls = []
        self.runners = []
        self.raw = {"id": 7, "uuid": "12345678-1234-1234-1234-123456789abc", "repo_id": 3,
                    "owner_id": 0, "name": module.NAME, "ephemeral": False}
        self.protection = module.api.desired_protection()

    def request(self, method, path, body=None):
        self.calls.append((method, path, body))
        if path == "/api/v1/version":
            return {"version": "17.0.1"}
        if path == module.BASE:
            return {"full_name": "MrJ-am/mrjam-validation", "id": 3, "archived": False, "mirror": False,
                    "default_branch": "main", "empty": False}
        if path.endswith("/branches/main"):
            return {"name": "main", "commit": {"id": self.rules}}
        if path.endswith("/branch_protections/main"):
            return copy.deepcopy(self.protection)
        if path == module.RUNNERS and method == "GET":
            return copy.deepcopy(self.runners)
        if path == module.RUNNERS and method == "POST":
            self.runners.append(self.raw)
            return {"id": self.raw["id"], "uuid": self.raw["uuid"], "token": "synthetic-token-1234567890"}
        if path == module.RUNNERS + "/7":
            return copy.deepcopy(self.raw)
        raise AssertionError("Unexpected fixture endpoint")


class RegistrationTests(unittest.TestCase):
    def setUp(self):
        self.api = Fixture()
        self.policy = {"rules_revision": self.api.rules}
        self.saved = []

    def register(self, existing=None):
        return module.register(self.api, self.policy, existing, lambda metadata, token: self.saved.append((metadata, token)))

    def test_scoped_registration_and_repeat_without_mutation(self):
        self.assertEqual(self.register()["decision"], "registered")
        self.assertEqual(len(self.saved), 1)
        self.assertEqual(self.register(self.saved[0][0])["decision"], "no-changes")
        self.assertEqual(len([call for call in self.api.calls if call[0] == "POST"]), 1)

    def test_refuses_rules_head_drift(self):
        self.api.rules = "b" * 40
        with self.assertRaisesRegex(module.api.Refused, "UNQUALIFIED_RULES_HEAD"):
            self.register()
        self.assertFalse(any(call[0] == "POST" for call in self.api.calls))

    def test_refuses_missing_protection(self):
        self.api.protection["enable_push"] = True
        with self.assertRaisesRegex(module.api.Refused, "UNQUALIFIED_PROTECTION"):
            self.register()

    def test_refuses_existing_unadopted_runner(self):
        self.api.runners = [self.api.raw]
        with self.assertRaisesRegex(module.api.Refused, "EXISTING_REGISTRATION_REQUIRES_ADOPTION"):
            self.register()
        self.assertFalse(any(call[0] == "POST" for call in self.api.calls))

    def test_refuses_any_existing_runner_instead_of_assuming_complete_pagination(self):
        self.api.runners = [{"name": "synthetic-unrelated-runner"}]
        with self.assertRaisesRegex(module.api.Refused, "EXISTING_REGISTRATION_REQUIRES_ADOPTION"):
            self.register()

    def test_refuses_identity_rebinding(self):
        self.register()
        self.api.raw["repo_id"] = 99
        with self.assertRaisesRegex(module.api.Refused, "REGISTRATION_CHANGED"):
            self.register(self.saved[0][0])

    def test_refuses_admin_other_repo_mutation_and_url(self):
        transport = module.Transport("synthetic-token-1234567890")
        for method, path in (("DELETE", module.RUNNERS + "/7"), ("POST", "/api/v1/admin/runners"),
                             ("GET", "https://example.invalid"), ("GET", module.RUNNERS + "/../registration-token"),
                             ("PATCH", module.BASE), ("GET", module.RUNNERS + "?page=2")):
            with self.assertRaisesRegex(module.api.Refused, "UNMANAGED_ENDPOINT"):
                transport.request(method, path)

    def test_credential_stored_private_and_not_config(self):
        self.register()
        metadata, token = self.saved[0]
        with tempfile.TemporaryDirectory() as temporary:
            root = os.open(temporary, os.O_RDONLY | os.O_DIRECTORY)
            try:
                module.store(root, metadata, token)
            finally:
                os.close(root)
            directory = Path(temporary) / "registration"
            self.assertEqual((directory / "runner-token").stat().st_mode & 0o777, 0o400)
            self.assertEqual((directory / "runner-token").read_text(), token + "\n")
            self.assertNotIn(token, (directory / "connection.json").read_text())
            self.assertNotIn(token, (directory / "identity.json").read_text())
            self.assertIn("$CREDENTIALS_DIRECTORY/runner-token", (directory / "connection.json").read_text())

    def test_no_production_network_docker_or_cache_in_config(self):
        self.register()
        value = module.configuration(self.saved[0][0])
        self.assertFalse(value["cache"]["enabled"])
        self.assertEqual(value["container"]["docker_host"], "-")
        self.assertEqual(value["runner"]["capacity"], 1)
        self.assertEqual(value["server"]["connections"]["mrjam-validation"]["url"], "http://127.0.0.1:3004")


if __name__ == "__main__":
    unittest.main()
