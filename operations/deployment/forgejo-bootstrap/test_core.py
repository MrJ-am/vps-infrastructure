"""Independent invented refusals and transient-token lifecycle tests."""
from contextlib import contextmanager
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("bootstrap_core", Path(__file__).with_name("core.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
TOKEN = "a" * 40


class Synthetic:
    def __init__(self):
        self.account = {"exists": True, "eligible": True, "legacy_exists": False, "legacy_local_admin": False}
        self.count = 0
        self.events = []
        self.revoked = False
        self.fail_request = False
        self.version = "17.0.1"
        self.organization = True
        self.issue_output = (TOKEN + "\n").encode()
        self.repo_identity_wrong = False
        self.refuse_revocation = False

    def sql(self, operation, label=None):
        self.events.append((operation, label))
        if operation == "account": return self.account.copy()
        if operation == "count": return self.count
        if operation == "revoke":
            if self.refuse_revocation: raise m.Refused("REVOKE_FAILED")
            self.count = 0

    def command(self, arguments, data=b""):
        self.events.append(("command", arguments))
        self.count = 1
        return self.issue_output

    def cleanup(self):
        if self.refuse_revocation: raise m.Refused("REVOKE_FAILED")
        if self.count:
            self.count = 0
            self.revoked = True

    def api(self, token):
        outer = self
        class API:
            def get(self, path):
                outer.events.append(("GET", path))
                if path.endswith("/version"): return 200, {"version": outer.version}
                if outer.revoked: return 401, None
                if path.endswith("/user"):
                    return 200, {"login": m.ACCOUNT, "is_admin": True, "email": "PRIVATE-UNEXPORTED"}
                if outer.fail_request: raise m.Refused("API_UNAVAILABLE")
                if path == "/api/v1/orgs/MrJ-am":
                    return (200, {"username": "MrJ-am", "description": "PRIVATE-UNEXPORTED"}) if outer.organization else (404, None)
                name = path.rsplit("/", 1)[-1]
                if name == "vision": return 404, None
                return 200, {"name": name, "full_name": ("different/" if outer.repo_identity_wrong else "MrJ-am/") + name,
                             "permissions": {"admin": True}, "empty": False, "default_branch": "main", "description": "PRIVATE-UNEXPORTED"}
        return API()

    @contextmanager
    def installed(self):
        with patch.object(m, "validate_configuration"), patch.object(m, "validate_running"), patch.object(m, "identity_attested", return_value=True), \
                patch.object(m, "sql", side_effect=self.sql), patch.object(m, "API", side_effect=self.api), \
                patch.object(m, "command", side_effect=self.command), patch.object(m, "cleanup", side_effect=self.cleanup), \
                patch.object(m, "publish", side_effect=lambda *x: self.events.append(("publish", x))):
            yield


class ClosedTests(unittest.TestCase):
    def test_forgejo_global_settings_do_not_supply_security_defaults(self):
        profile = b"APP_NAME=Invented\nRUN_MODE=prod\n[service]\nENABLE_INTERNAL_SIGNIN=false\nENABLE_BASIC_AUTHENTICATION=false\nENABLE_NOTIFY_MAIL=false\n[database]\nDB_TYPE=postgres\nHOST=/run/postgresql\nNAME=forgejo\nUSER=forgejo\nAUTO_MIGRATION=false\n[server]\nHTTP_ADDR=127.0.0.1\nHTTP_PORT=3004\n"
        with patch.object(m, "private_file", return_value=profile):
            m.validate_configuration()
        for invalid in (profile.replace(b"ENABLE_INTERNAL_SIGNIN=false", b"ENABLE_INTERNAL_SIGNIN=true"),
                        profile.replace(b"ENABLE_BASIC_AUTHENTICATION=false", b"ENABLE_BASIC_AUTHENTICATION=true"),
                        b"ENABLE_BASIC_AUTHENTICATION=false\n" + profile.replace(b"ENABLE_BASIC_AUTHENTICATION=false\n", b""),
                        profile + b"[__forbidden_default__]\nENABLE_BASIC_AUTHENTICATION=false\n"):
            with patch.object(m, "private_file", return_value=invalid), self.assertRaises(m.Refused):
                m.validate_configuration()

    def test_duplicate_nonfinite_and_oversize_json_refused(self):
        for value in (b'{"x":1,"x":2}', b'{"x":NaN}', b"x" * (m.LIMIT + 1)):
            with self.assertRaises(m.Refused): m.parse(value)

    def test_cli_input_cannot_select_mode_path_or_command(self):
        for mode, args in (("probe", ["/etc/shadow"]), ("bootstrap", ["--username", "MrJam"]), ("delete", [])):
            with patch.object(m, "locked") as lock:
                self.assertEqual(m.main(mode, args), 64)
                lock.assert_not_called()

    def test_no_unmanaged_api_or_sql_can_be_selected(self):
        api = m.API(TOKEN)
        for path in ("https://outside.invalid/", "/api/v1/users", "/api/v1/admin/users", "/api/v1/repos/MrJ-am/vision/contents/private", "/api/v1/repos/other/vision", "/api/v1/orgs/MrJ-am/members"):
            with self.assertRaises(m.Refused): api.get(path)
        for name in ("SELECT 1", "users", "DROP DATABASE forgejo"):
            with self.assertRaises(m.Refused): m.sql(name)

    def test_label_injection_and_other_user_refused_before_command(self):
        with patch.object(m, "command") as command:
            for label in ("'; DELETE FROM access_token;--", "MrJam", "mrjam-governance-lease-../", "a" * 300):
                with self.assertRaises(m.Refused): m.sql("revoke", label)
            command.assert_not_called()

    def test_literal_sql_only_selects_booleans_and_exact_account_token(self):
        self.assertNotIn("passwd", m.ACCOUNT_SQL)
        self.assertNotIn("email", m.ACCOUNT_SQL)
        self.assertNotIn("token_hash", m.COUNT_SQL + m.REVOKE_SQL)
        self.assertIn("AND name=:'lease'", m.REVOKE_SQL)
        self.assertIn("lower_name='mrjam-governance-bootstrap'", m.REVOKE_SQL)
        with patch.object(m, "command", return_value=b"2\n"):
            with self.assertRaisesRegex(m.Refused, "LEASE_COLLISION"):
                m.sql("count", "mrjam-governance-lease-" + "b" * 32)

    def test_probe_filters_private_fields_and_never_creates(self):
        fake = Synthetic()
        with fake.installed(): value = m.probe()
        self.assertTrue(value["temporary_token_revoked"])
        self.assertFalse(value["repositories"]["vision"]["exists"])
        self.assertNotIn("PRIVATE", json.dumps(value))
        commands = [value for name, value in fake.events if name == "command"]
        self.assertEqual(len(commands), 1)
        self.assertIn("generate-access-token", commands[0])
        self.assertIn(m.READ_SCOPES, commands[0])
        self.assertNotIn("create", commands[0])
        self.assertEqual(fake.count, 0)

    def test_missing_account_does_not_generate_token_or_claim_missing_org(self):
        fake = Synthetic()
        fake.account.update(exists=False, eligible=False)
        with fake.installed(): value = m.probe()
        self.assertIsNone(value["organization_exists"])
        self.assertIsNone(value["temporary_token_revoked"])
        self.assertFalse(any(name == "command" for name, _ in fake.events))

    def test_personally_bound_old_account_never_used_as_fallback(self):
        fake = Synthetic()
        fake.account.update(exists=False, eligible=False, legacy_exists=True, legacy_local_admin=False)
        with fake.installed(): value = m.probe()
        self.assertTrue(value["legacy_admin_exists"])
        self.assertFalse(any(name == "command" for name, _ in fake.events))

    def test_unknown_authenticated_version_refuses_and_revokes_token(self):
        fake = Synthetic()
        fake.version = "16.0.3"
        with fake.installed(), self.assertRaisesRegex(m.Refused, "VERSION"): m.probe()
        self.assertTrue(fake.revoked)
        self.assertEqual(fake.count, 0)

    def test_transport_failure_revokes_without_disclosing_input(self):
        fake = Synthetic()
        fake.fail_request = True
        with fake.installed(), self.assertRaisesRegex(m.Refused, "API_UNAVAILABLE"): m.probe()
        self.assertTrue(fake.revoked)
        self.assertEqual(fake.count, 0)

    def test_cli_malformed_output_still_revokes_new_token(self):
        fake = Synthetic()
        fake.issue_output = b"SENSITIVE-DIAGNOSTIC\n"
        with fake.installed(), self.assertRaisesRegex(m.Refused, "TOKEN_FORMAT_REFUSED"): m.probe()
        self.assertTrue(fake.revoked)

    def test_repository_identity_change_refuses_and_revokes(self):
        fake = Synthetic()
        fake.repo_identity_wrong = True
        with fake.installed(), self.assertRaisesRegex(m.Refused, "REPOSITORY_SHAPE_REFUSED"): m.probe()
        self.assertTrue(fake.revoked)

    def test_wrong_scopes_refused_without_issuing(self):
        fake = Synthetic()
        with fake.installed(), self.assertRaises(m.Refused):
            with m._lease("all"): pass
        self.assertFalse(any(name == "command" for name, _ in fake.events))

    def test_non_admin_or_unattested_technical_account_cannot_issue(self):
        fake = Synthetic()
        fake.account["eligible"] = False
        with fake.installed(), self.assertRaises(m.Refused):
            with m._lease(m.READ_SCOPES): pass
        self.assertFalse(any(name == "command" for name, _ in fake.events))

    def test_scope_lease_always_revokes_when_backend_body_raises(self):
        fake = Synthetic()
        with fake.installed(), self.assertRaisesRegex(RuntimeError, "synthetic"):
            with m._lease(m.WRITE_SCOPES): raise RuntimeError("synthetic")
        self.assertTrue(fake.revoked)

    def test_probe_does_not_create_missing_organization(self):
        fake = Synthetic()
        fake.organization = False
        with fake.installed(): value = m.probe()
        self.assertFalse(value["organization_exists"])
        self.assertTrue(all(name != "POST" for name, _ in fake.events))

    def test_private_reader_rejects_parent_symlink_leaf_symlink_and_hardlink(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = root / "folder"
            folder.mkdir()
            actual = folder / "actual"
            actual.write_bytes(b"PRIVATE")
            actual.chmod(0o600)
            self.assertEqual(m.private_file(actual, owner=os.getuid()), b"PRIVATE")
            link = root / "linked"
            link.symlink_to(folder, target_is_directory=True)
            with self.assertRaises(OSError): m.private_file(link / "actual", owner=os.getuid())
            leaf = folder / "leaf"
            leaf.symlink_to(actual)
            with self.assertRaises(OSError): m.private_file(leaf, owner=os.getuid())
            os.link(actual, folder / "hardlink")
            with self.assertRaises(m.Refused): m.private_file(actual, owner=os.getuid())

    def test_permissive_wrong_owner_or_fifo_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary, "input")
            path.write_bytes(b"PRIVATE")
            path.chmod(0o644)
            with self.assertRaises(m.Refused): m.private_file(path, owner=os.getuid())
            path.chmod(0o600)
            with self.assertRaises(m.Refused): m.private_file(path, owner=os.getuid()+1)
            path.unlink()
            os.mkfifo(path)
            with self.assertRaises(m.Refused): m.private_file(path, owner=os.getuid())


if __name__ == "__main__":
    unittest.main()
