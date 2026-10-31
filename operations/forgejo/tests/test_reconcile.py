"""Synthetic transport and loopback-only HTTP refusals for the API controller."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("reconcile", ROOT / "reconcile.py")
reconcile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reconcile)


def policy(names=("mrjam-plateforme", "mrjam-validation", "vps-infrastructure"), phase="bootstrap-repositories"):
    return {"schema_version": 2, "owner": "MrJ-am", "forgejo_version": "17.0.1", "rules_revision": "1" * 40,
            "controller_revision": "2" * 40, "phase": phase, "repositories": sorted(names)}


class FakeAPI:
    def __init__(self):
        self.version = "17.0.1"
        self.repos = {}
        self.calls = []
        self.on_call = None
        self.next_id = 1
        self.rules_head = "1" * 40

    def request(self, method, path, body=None, missing=False):
        if not reconcile.allowed_request(method, path):
            raise reconcile.Refused("UNMANAGED_ENDPOINT")
        self.calls.append((method, path, copy.deepcopy(body)))
        if self.on_call:
            self.on_call(self, method, path, body)
        if path == "/api/v1/version":
            return {"version": self.version}
        if method == "POST" and path.endswith("/repos"):
            name = body["name"]
            self.repos[name] = {"name": name, "id": self.next_id, "full_name": "MrJ-am/" + name, "private": True,
                                "archived": False, "mirror": False, "empty": True, "has_actions": True, "default_branch": "main", "protection": None}
            self.next_id += 1
            return copy.deepcopy(self.repos[name])
        name = path.split("/")[5]
        current = self.repos.get(name)
        if current is None:
            if missing:
                return None
            raise reconcile.Refused("API_REJECTED")
        if "branch_protections" in path:
            if method != "GET":
                current["protection"] = {**(current["protection"] or {}), **copy.deepcopy(body)}
            return copy.deepcopy(current["protection"])
        if path.endswith("/branches/main"):
            return {"name": "main", "commit": {"id": self.rules_head}}
        if method == "PATCH":
            current.update(body)
        return copy.deepcopy(current)

    def create(self, name="mrjam-plateforme"):
        self.request("POST", "/api/v1/orgs/MrJ-am/repos", {"name": name})
        self.calls.clear()
        return self.repos[name]


class ReconcileTests(unittest.TestCase):
    def setUp(self):
        self.api = FakeAPI()
        self.policy = policy()
        self.used = set()

    def consume(self, value):
        if value in self.used:
            raise reconcile.Refused("PLAN_ALREADY_USED")
        self.used.add(value)

    def approved(self):
        return reconcile.plan(self.policy, reconcile.observe(self.api, self.policy), now=100)

    def execute(self, approved=None, now=100):
        return reconcile.apply(self.api, self.policy, self.approved() if approved is None else approved, consume=self.consume, now=now)

    def test_create_protect_and_repeat_is_idempotent(self):
        approved = self.approved()
        self.assertEqual(self.execute(approved)["operations_applied"], 3)
        for repo in self.api.repos.values():
            repo["empty"] = False # Exact sources are imported by a distinct code-only operation.
        self.policy["phase"] = "protect-main"
        approved = self.approved()
        self.assertEqual(self.execute(approved)["operations_applied"], 3)
        self.assertEqual(set(self.api.repos), set(self.policy["repositories"]))
        for repo in self.api.repos.values():
            self.assertTrue(repo["private"])
            self.assertFalse(repo["has_actions"])
            self.assertEqual(repo["protection"], reconcile.desired_protection())
        self.api.calls.clear()
        self.assertEqual(self.execute(approved)["decision"], "no-changes")
        self.assertTrue(all(method == "GET" for method, _, _ in self.api.calls))

    def test_empty_repository_requires_code_import_before_protection(self):
        self.execute()
        self.policy["phase"] = "protect-main"
        with self.assertRaisesRegex(reconcile.Refused, "SOURCE_IMPORT_REQUIRED"):
            self.approved()

    def operated(self):
        self.execute()
        for repo in self.api.repos.values():
            repo["empty"] = False
        self.policy["phase"] = "protect-main"
        self.execute()
        self.policy["phase"] = "operate-validation"

    def test_enable_actions_only_for_protected_pinned_validation_repo(self):
        self.operated()
        self.assertEqual(self.execute()["operations_applied"], 1)
        self.assertEqual({name for name, repo in self.api.repos.items() if repo["has_actions"]}, {"mrjam-validation"})
        self.assertEqual(self.execute()["decision"], "no-changes")

    def test_enable_actions_rejects_changed_rules_head(self):
        self.operated()
        self.api.rules_head = "f" * 40
        with self.assertRaisesRegex(reconcile.Refused, "UNQUALIFIED_RULES_HEAD"):
            self.approved()

    def test_enable_actions_rejects_weakened_protection(self):
        self.operated()
        self.api.repos["mrjam-validation"]["protection"]["enable_push"] = True
        with self.assertRaisesRegex(reconcile.Refused, "UNQUALIFIED_PROTECTION"):
            self.approved()

    def test_enable_actions_checks_head_again_before_mutation(self):
        self.operated()
        approved = self.approved()
        reads = 0
        def race(api, method, path, body):
            nonlocal reads
            if method == "GET" and path.endswith("/branches/main"):
                reads += 1
                if reads == 2:
                    api.rules_head = "f" * 40
        self.api.on_call = race
        with self.assertRaisesRegex(reconcile.Refused, "UNQUALIFIED_RULES_HEAD"):
            self.execute(approved)
        self.assertFalse(self.api.repos["mrjam-validation"]["has_actions"])

    def test_public_existing_repository_keeps_its_visibility(self):
        repo = self.api.create()
        repo["private"] = False
        self.execute()
        self.assertFalse(repo["private"])
        self.assertFalse(any("private" in (body or {}) for method, path, body in self.api.calls if method == "PATCH"))

    def test_unmanaged_objects_are_never_requested(self):
        self.execute()
        self.assertTrue(all("M-moire" not in path and "Motion" not in path for _, path, _ in self.api.calls))
        self.assertFalse(any(method == "DELETE" for method, _, _ in self.api.calls))

    def test_wrong_version_refused_before_write(self):
        self.api.version = "16.0.3"
        with self.assertRaisesRegex(reconcile.Refused, "UNQUALIFIED_FORGEJO_VERSION"):
            self.execute()
        self.assertEqual(len(self.api.calls), 1)

    def test_policy_arbitrary_owner_repo_or_extra_fields_refused(self):
        for key, value in (("owner", "elsewhere"), ("repositories", ["M-moire"]), ("url", "http://secret.invalid"), ("rules_revision", None)):
            changed = copy.deepcopy(self.policy)
            changed[key] = value
            with self.subTest(key=key), self.assertRaises(reconcile.Refused):
                reconcile.validate_policy(changed)

    def test_stale_observation_prevents_all_mutations(self):
        approved = self.approved()
        self.api.create()
        with self.assertRaisesRegex(reconcile.Refused, "STALE_OR_CHANGED_PLAN"):
            self.execute(approved)
        self.assertTrue(all(method == "GET" for method, _, _ in self.api.calls))
        self.assertFalse(self.used)

    def test_modified_operation_is_not_an_arbitrary_request(self):
        approved = self.approved()
        approved["operations"][0]["operation"] = "delete"
        with self.assertRaisesRegex(reconcile.Refused, "STALE_OR_CHANGED_PLAN"):
            self.execute(approved)

    def test_expiry_and_future_plan_refused(self):
        for now in (99, 3701):
            with self.subTest(now=now), self.assertRaisesRegex(reconcile.Refused, "PLAN_EXPIRED"):
                self.execute(self.approved(), now=now)

    def test_state_changes_between_global_observation_and_write_refused(self):
        self.api.create()
        approved = self.approved()
        reads = 0
        def race(api, method, path, body):
            nonlocal reads
            if method == "GET" and path == reconcile.path_for("mrjam-plateforme"):
                reads += 1
                if reads == 2:
                    api.repos["mrjam-plateforme"]["id"] += 10
        self.api.on_call = race
        with self.assertRaisesRegex(reconcile.Refused, "STATE_CHANGED_BEFORE_WRITE"):
            self.execute(approved)
        self.assertFalse(any(method != "GET" for method, _, _ in self.api.calls))

    def test_consumed_plan_is_refused_before_write(self):
        approved = self.approved()
        self.used.add(reconcile.digest(approved))
        with self.assertRaisesRegex(reconcile.Refused, "PLAN_ALREADY_USED"):
            self.execute(approved)

    def test_readback_catches_ignored_setting(self):
        self.api.create()
        approved = self.approved()
        def ignore(api, method, path, body):
            if method == "PATCH" and body == {"has_actions": False}:
                body["has_actions"] = True
        self.api.on_call = ignore
        with self.assertRaisesRegex(reconcile.Refused, "READBACK_FAILED"):
            self.execute(approved)

    def test_identity_metadata_is_filtered_not_echoed(self):
        repo = self.api.create()
        repo.update({"description": "SYNTHETIC_PERSONAL_MARKER", "owner": {"email": "SYNTHETIC_PERSONAL_MARKER"}})
        result = reconcile.observe(self.api, self.policy)
        self.assertNotIn("SYNTHETIC_PERSONAL_MARKER", json.dumps(result))

    def test_existing_identity_allowlists_are_refused_without_names(self):
        repo = self.api.create()
        repo["protection"] = reconcile.desired_protection()
        repo["protection"]["push_whitelist_usernames"] = ["SYNTHETIC_PERSONAL_MARKER"]
        with self.assertRaisesRegex(reconcile.Refused, "EXISTING_POLICY_REQUIRES_ADOPTION") as caught:
            self.approved()
        self.assertNotIn("SYNTHETIC_PERSONAL_MARKER", str(caught.exception))

    def test_stronger_existing_protection_is_not_weakened(self):
        for field, value in (("required_approvals", 2), ("require_signed_commits", True), ("enable_merge_whitelist", True), ("enable_approvals_whitelist", True)):
            repo = self.api.create()
            repo["protection"] = reconcile.desired_protection()
            repo["protection"][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(reconcile.Refused, "STRONGER_EXISTING_POLICY"):
                self.approved()

    def test_alternate_branch_archive_and_mirror_adoption_refused(self):
        for field, value in (("default_branch", "master"), ("archived", True), ("mirror", True)):
            repo = self.api.create()
            repo[field] = value
            with self.subTest(field=field), self.assertRaises(reconcile.Refused):
                self.approved()

    def test_token_reader_refuses_symlink_world_readable_fifo_and_newline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            token = root / "credential"
            token.write_text("x" * 40)
            token.chmod(0o600)
            self.assertEqual(reconcile.document(token, credential=True), "x" * 40)
            link = root / "link"
            link.symlink_to(token)
            with self.assertRaises(reconcile.Refused):
                reconcile.document(link, credential=True)
            token.chmod(0o644)
            with self.assertRaisesRegex(reconcile.Refused, "UNSAFE_CREDENTIAL"):
                reconcile.document(token, credential=True)
            fifo = root / "fifo"
            os.mkfifo(fifo)
            with self.assertRaises(reconcile.Refused):
                reconcile.document(fifo, credential=True)
            token.chmod(0o600)
            token.write_text("x" * 30 + "\nInjected: yes")
            with self.assertRaises(reconcile.Refused):
                reconcile.document(token, credential=True)

    def credential_fixture(self, *, file_acl=None, parent_acl=None, readonly=True):
        uid = 64551
        info = SimpleNamespace(st_uid=0, st_gid=0, st_mode=0o100440, st_dev=1, st_ino=2)
        parent = SimpleNamespace(st_uid=0, st_gid=0, st_mode=0o40550, st_dev=1, st_ino=3)
        ancestor = SimpleNamespace(st_uid=0, st_gid=0, st_mode=0o40755)
        with patch.object(reconcile.os, "getuid", return_value=uid), \
             patch.object(reconcile.os, "getxattr", side_effect=[reconcile.credential_acl(uid, 4) if file_acl is None else file_acl,
                                                                reconcile.credential_acl(uid, 5) if parent_acl is None else parent_acl]), \
             patch.object(reconcile.os, "fstatvfs", return_value=SimpleNamespace(f_flag=os.ST_RDONLY if readonly else 0)), \
             patch.object(reconcile.os, "lstat", return_value=ancestor), \
             patch.object(reconcile.os, "open", side_effect=[10, 11]), \
             patch.object(reconcile.os, "fstat", side_effect=[parent, info]), \
             patch.object(reconcile.os, "close"):
            reconcile.systemd_credential_permissions(reconcile.CREDENTIAL_PATH, 9, info)

    def test_systemd_credential_accepts_only_measured_named_acl_on_readonly_mount(self):
        self.credential_fixture()

    def test_systemd_credential_rejects_group_read_or_another_named_identity(self):
        for raw in (reconcile.credential_acl(64552, 4), reconcile.credential_acl(64551, 5), b"invalid"):
            with self.subTest(raw=raw), self.assertRaisesRegex(reconcile.Refused, "UNSAFE_CREDENTIAL"):
                self.credential_fixture(file_acl=raw)

    def test_systemd_credential_rejects_writable_mount(self):
        with self.assertRaisesRegex(reconcile.Refused, "UNSAFE_CREDENTIAL"):
            self.credential_fixture(readonly=False)

    def test_systemd_credential_rejects_parent_for_another_identity(self):
        with self.assertRaisesRegex(reconcile.Refused, "UNSAFE_CREDENTIAL"):
            self.credential_fixture(parent_acl=reconcile.credential_acl(64552, 5))

    def test_json_duplicates_and_nonfinite_numbers_refused(self):
        for value in (b'{"x":1,"x":2}', b'{"x":NaN}', b'x' * (reconcile.MAX_BYTES + 1)):
            with self.subTest(value=value[:20]), self.assertRaises(reconcile.Refused):
                reconcile.parse(value)

    def test_cli_rejects_arbitrary_paths_and_urls_without_echo(self):
        result = subprocess.run([sys.executable, "-I", "-S", str(ROOT / "reconcile.py"), "http://SYNTHETIC_PRIVATE_MARKER"], capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr, b"")
        self.assertNotIn(b"SYNTHETIC_PRIVATE_MARKER", result.stdout)


class HTTPTests(unittest.TestCase):
    def serve(self, response):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                status, headers, body = response
                self.send_response(status)
                for key, value in headers.items():
                    self.send_header(key, value)
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (ConnectionResetError, BrokenPipeError):
                    pass
            def log_message(self, *args):
                pass
        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: thread.join(2))
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return reconcile.Transport("synthetic-token-" + "x" * 30, synthetic_port=server.server_port)

    def test_local_version_response(self):
        api = self.serve((200, {"Content-Type": "application/json"}, b'{"version":"17.0.1"}'))
        self.assertEqual(api.request("GET", "/api/v1/version"), {"version": "17.0.1"})

    def test_redirect_refused_before_follow(self):
        api = self.serve((302, {"Location": "http://SYNTHETIC_SECRET.invalid/"}, b""))
        with self.assertRaisesRegex(reconcile.Refused, "REDIRECT_REFUSED"):
            api.request("GET", "/api/v1/version")

    def test_wrong_content_type_gzip_overlimit_and_error_refused(self):
        for status, headers, body in ((200, {"Content-Type": "text/html"}, b"SYNTHETIC_SECRET"),
                                      (200, {"Content-Type": "application/json", "Content-Encoding": "gzip"}, b"x"),
                                      (200, {"Content-Type": "application/json", "Content-Length": "131073"}, b"x"),
                                      (500, {"Content-Type": "application/json"}, b"SYNTHETIC_SECRET")):
            api = self.serve((status, headers, body))
            with self.subTest(status=status, headers=headers), self.assertRaises(reconcile.Refused) as caught:
                api.request("GET", "/api/v1/version")
            self.assertNotIn("SYNTHETIC_SECRET", str(caught.exception))

    def test_endpoints_and_methods_refused_before_network(self):
        api = reconcile.Transport("x" * 40, synthetic_port=65530)
        for method, path in (("GET", "/api/v1/admin/users"), ("DELETE", reconcile.path_for("mrjam-plateforme")), ("GET", "/api/v1/repos/MrJ-am/M-moire"), ("GET", "http://127.0.0.1:9999")):
            with self.subTest(method=method, path=path), self.assertRaisesRegex(reconcile.Refused, "UNMANAGED_ENDPOINT"):
                api.request(method, path)


if __name__ == "__main__":
    unittest.main()
