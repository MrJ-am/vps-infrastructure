"""Refusal boundaries; these tests never contact Docker or PostgreSQL."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("runtime_browser_fixture", HERE / "fixture.py")
FIXTURE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FIXTURE)


class Boundaries(unittest.TestCase):
    def test_wrong_database_is_refused_before_any_path_or_command(self):
        for value in ("", "postgresql://marker-must-not-be-echoed@elsewhere.invalid/a", FIXTURE.URL + "?options=anything"):
            env = {k: v for k, v in os.environ.items() if not k.startswith("PG")}
            env["MRJAM_SYNTHETIC_DATABASE_URL"] = value
            result = subprocess.run([sys.executable, str(HERE / "fixture.py"), "setup", "/nonexistent", "/nonexistent"], env=env, capture_output=True, check=False)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stderr), {"code": "SYNTHETIC_DATABASE_REQUIRED"})
            self.assertEqual(result.stdout, b"")

    def test_ambient_postgres_configuration_is_refused(self):
        with patch.dict(os.environ, {"MRJAM_SYNTHETIC_DATABASE_URL": FIXTURE.URL, "PGSERVICE": "unread-synthetic-marker"}, clear=True):
            with self.assertRaisesRegex(FIXTURE.Refused, "AMBIENT_DATABASE_CONFIGURATION_REFUSED"):
                FIXTURE.guard()

    def test_only_disposable_directory_name_and_private_permissions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "mrjam-runtime-browser-0123456789abcdef"
            root.mkdir(mode=0o700)
            self.assertEqual(FIXTURE.workdir(str(root)), (root, "rb_0123456789abcdef"))
            root.chmod(0o755)
            with self.assertRaises(FIXTURE.Refused):
                FIXTURE.workdir(str(root))
            root.chmod(0o700)
            link = Path(temporary) / "mrjam-runtime-browser-fedcba9876543210"
            link.symlink_to(root)
            with self.assertRaises(FIXTURE.Refused):
                FIXTURE.workdir(str(link))

    def test_vision_principals_remain_identical_to_literal_rls_policies(self):
        roles = FIXTURE.role_names("rb_0123456789abcdef")
        for name in FIXTURE.VISION_ROLES:
            self.assertEqual(roles[name], name)
        for name in ("collecte", "science", "audition"):
            self.assertEqual(roles[name], "rb_0123456789abcdef_" + name)
        migration = (FIXTURE.PLATFORM / "components/vision/migrations/019_comptes_quotas.sql").read_text()
        self.assertIn("current_user='vision_migration'", migration)
        with self.assertRaises(FIXTURE.Refused):
            FIXTURE.role_names("invalid;drop")

    def test_database_dispatch_refuses_non_fixture_names_before_docker(self):
        with patch.object(FIXTURE, "docker") as call:
            for name in ("postgres", "vision", "mrjam_synthetic;SELECT", "rb_abc_vision"):
                with self.assertRaises(FIXTURE.Refused):
                    FIXTURE.sql(name, "SELECT 1")
            call.assert_not_called()

    def test_cleanup_refuses_forged_object_set_before_sql(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = {"prefix": "rb_0123456789abcdef", "marker": "mrjam-runtime-browser:rb_0123456789abcdef",
                     "created_roles": ["unrelated_role"], "created_databases": []}
            (root / "fixture.json").write_text(json.dumps(state))
            with patch.object(FIXTURE, "sql") as query:
                with self.assertRaisesRegex(FIXTURE.Refused, "FIXTURE_OBJECT_SET_REFUSED"):
                    FIXTURE.cleanup(root, state["prefix"])
                query.assert_not_called()

    def test_cleanup_requires_marker_for_every_object_before_any_drop(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prefix = "rb_0123456789abcdef"
            state = {"prefix": prefix, "marker": "mrjam-runtime-browser:" + prefix,
                     "created_roles": ["vision"], "created_databases": [prefix + "_mateval"]}
            (root / "fixture.json").write_text(json.dumps(state))
            with patch.object(FIXTURE, "sql", side_effect=[state["marker"], "someone_else"]) as query:
                with self.assertRaisesRegex(FIXTURE.Refused, "FIXTURE_OWNERSHIP_REFUSED"):
                    FIXTURE.cleanup(root, prefix)
                self.assertEqual(query.call_count, 2)
                self.assertTrue(all(call.args[1].startswith("SELECT ") for call in query.call_args_list))

    def test_private_files_are_exclusive_and_never_follow_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target"
            FIXTURE.private(target, b"invented-only")
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            link = root / "link"
            link.symlink_to(target)
            with self.assertRaises(OSError):
                FIXTURE.private(link, b"replacement")
            self.assertEqual(target.read_bytes(), b"invented-only")


if __name__ == "__main__":
    unittest.main()
