"""Synthetic tests of the development helper's meaningful safety properties."""

from contextlib import redirect_stdout
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("mrjam_environment", BASE / "environment.py")
assert SPEC and SPEC.loader
env = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(env)


class EnvironmentTests(unittest.TestCase):
    def test_malformed_lock_has_fixed_error_without_content(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            shutil.copyfile(BASE / "environment.py", root / "environment.py")
            marker = "SYNTHETIC_SECRET_BAD_JSON"
            (root / "toolchains.lock.json").write_text(marker)
            result = subprocess.run([sys.executable, str(root / "environment.py"), "check"],
                                    capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stderr, "")
            self.assertNotIn(marker, result.stdout)
            self.assertEqual(json.loads(result.stdout)["code"], "LOCKFILE_UNAVAILABLE")

    def test_invalid_arguments_do_not_echo_values(self):
        marker = "SYNTHETIC_SECRET_ARGUMENT"
        output = io.StringIO()
        with patch.object(env.sys, "argv", ["environment.py", marker]), redirect_stdout(output):
            with self.assertRaises(SystemExit) as caught:
                env.main()
        self.assertEqual(caught.exception.code, 2)
        self.assertNotIn(marker, output.getvalue())
        self.assertEqual(json.loads(output.getvalue())["code"], "INVALID_ARGUMENTS")

    def test_failed_process_diagnostic_is_never_exposed(self):
        marker = "SYNTHETIC_SECRET_MARKER_DO_NOT_RETURN"
        with patch.object(env, "command", return_value=(1, marker)):
            with self.assertRaises(env.SetupError) as caught:
                env.require_command(["synthetic"], "SYNTHETIC_FAILURE")
        self.assertEqual(str(caught.exception), "SYNTHETIC_FAILURE")
        self.assertNotIn(marker, str(caught.exception))

    def test_docker_cannot_follow_inherited_remote_selector(self):
        with patch.dict(os.environ, {"DOCKER_HOST": "tcp://synthetic.invalid:2375",
                                     "DOCKER_CONTEXT": "synthetic-remote",
                                     "DOCKER_CONFIG": "/synthetic/config",
                                     "HTTPS_PROXY": "http://synthetic-proxy:8080"}):
            with patch.object(env, "command", return_value=(0, "")) as run:
                env.docker(["info"])
        args, kwargs = run.call_args
        self.assertEqual(args[0][:2], ["docker", "--host=unix:///var/run/docker.sock"])
        for name in env.DOCKER_SELECTORS:
            self.assertNotIn(name, kwargs["env"])
        self.assertEqual(kwargs["env"]["DOCKER_CONFIG"], "/synthetic/config")
        self.assertEqual(kwargs["env"]["HTTPS_PROXY"], "http://synthetic-proxy:8080")

    def test_versions_reject_wrong_release_and_unexpected_diagnostics(self):
        for value in ("v24.20.0", "v24.19.0\nSYNTHETIC_SECRET", "v24.19.00"):
            with patch.object(env, "command", return_value=(0, value)):
                self.assertFalse(env.version_ok(["node"], "24.19.0", prefix="v"))
        with patch.object(env, "command", return_value=(0, "rustc 1.99.1 (58cf8f9c3 2026-10-13)\n")):
            self.assertTrue(env.version_ok(["rustc"], "1.99.1", prefix="rustc "))

    def test_service_arguments_restrict_bindings_and_resources(self):
        for service, port in (("postgres", "127.0.0.1:55432:5432"),
                              ("nginx", "127.0.0.1:18080:8080")):
            args = env.run_arguments(service)
            self.assertIn(port, args)
            self.assertIn("--read-only", args)
            self.assertIn("--cap-drop=ALL", args)
            self.assertIn("--security-opt=no-new-privileges=true", args)
            self.assertIn("--pids-limit=128", args)
            self.assertIn("--cpus=1", args)
            self.assertNotIn("--privileged", args)
            self.assertNotIn("--network=host", args)
            self.assertFalse(any("docker.sock" in arg for arg in args))
            self.assertIn("@sha256:", env.LOCK[service]["image"])
        self.assertFalse(any("type=bind" in arg for arg in env.run_arguments("postgres")))
        self.assertIn("/var/lib/postgresql/data:rw,nosuid,nodev,noexec,size=512m,uid=999,gid=999",
                      env.run_arguments("postgres"))

    def test_unrelated_container_cannot_be_removed(self):
        with patch.object(env, "docker", return_value=(0, "")), \
             patch.object(env, "owned", return_value=False), \
             patch.object(env, "require_docker") as mutate:
            with self.assertRaisesRegex(env.SetupError, "SYNTHETIC_CONTAINER_COLLISION"):
                env.services_down()
        mutate.assert_not_called()

    def test_unknown_service_has_no_general_run_interface(self):
        with self.assertRaises((env.SetupError, KeyError)):
            env.run_arguments("run-arbitrary-command")

    def test_extension_initialization_refuses_unowned_container(self):
        with patch.object(env, "container_compatible", return_value=False), \
             patch.object(env, "docker") as inspect, \
             patch.object(env, "require_docker") as mutate:
            with self.assertRaisesRegex(env.SetupError, "SYNTHETIC_CONTAINER_COLLISION"):
                env.initialize_postgres_fixture()
        inspect.assert_not_called()
        mutate.assert_not_called()

    def test_extension_initialization_has_only_literal_synthetic_target(self):
        with patch.object(env, "container_compatible", return_value=True), \
             patch.object(env, "docker", return_value=(0, "ready")), \
             patch.object(env, "require_docker") as execute:
            self.assertTrue(env.initialize_postgres_fixture())
        args = execute.call_args.args[0]
        self.assertEqual(args[:2], ["exec", env.CONTAINERS["postgres"]])
        self.assertIn("--dbname=mrjam_synthetic", args)
        self.assertIn("--username=mrjam_synthetic", args)
        self.assertIn("--set=ON_ERROR_STOP=1", args)
        self.assertIn("current_database() <> 'mrjam_synthetic'", args[-1])
        self.assertIn("CREATE EXTENSION IF NOT EXISTS vector", args[-1])

    def test_ready_database_without_pinned_extension_is_incomplete(self):
        with patch.object(env, "container_compatible", side_effect=lambda c: c == env.CONTAINERS["postgres"]), \
             patch.object(env, "docker", side_effect=[(0, "t\n"), (0, "170011|missing\n")]), \
             patch.object(env.socket, "create_connection"):
            status = env.service_status()
        self.assertTrue(status["postgres_synthetic"])
        self.assertTrue(status["postgres_version"])
        self.assertFalse(status["postgres_pgvector"])

    def test_download_hash_mismatch_is_rejected_and_removed(self):
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / "archive"
            with patch.object(env.urllib.request, "urlopen", return_value=io.BytesIO(b"synthetic changed archive")):
                with self.assertRaisesRegex(env.SetupError, "RUST_DIGEST_MISMATCH"):
                    env.download_verified("https://static.rust-lang.org/dist/synthetic", destination, "0" * 64)
            self.assertFalse(destination.exists())

    def test_download_refuses_other_sources_before_network(self):
        with patch.object(env.urllib.request, "urlopen") as request:
            with self.assertRaisesRegex(env.SetupError, "DOWNLOAD_SOURCE_NOT_ALLOWED"):
                env.download_verified("https://synthetic.invalid/archive", Path("unused"), "0" * 64)
        request.assert_not_called()

    def test_bundle_hash_detects_resource_substitution_and_path_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "resource").write_bytes(b"synthetic original")
            first = env.bundle_digest(root, set())
            (root / "resource").write_bytes(b"synthetic altered")
            second = env.bundle_digest(root, set())
            self.assertNotEqual(first, second)
            (root / "resource").write_bytes(b"synthetic original")
            (root / "resource").rename(root / "different-path")
            self.assertNotEqual(first, env.bundle_digest(root, set()))

    def test_node_check_never_installs_or_replaces_tool(self):
        with patch.object(env, "version_ok", return_value=False), \
             patch.object(env, "require_command") as installer:
            with self.assertRaisesRegex(env.SetupError, "NODE_PIN_MISMATCH"):
                env.check_node()
        installer.assert_not_called()

    def test_changed_lock_invalidates_cached_install(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            local = root / ".local"
            local.mkdir()
            (root / "package.json").write_text('{}')
            (root / "package-lock.json").write_text('{"synthetic_version": 1}')
            with patch.object(env, "BASE", root), patch.object(env, "LOCAL", local):
                (local / "npm.fingerprint").write_text(env.npm_fingerprint())
                self.assertTrue(env.npm_lock_current())
                (root / "package-lock.json").write_text('{"synthetic_version": 2}')
                self.assertFalse(env.npm_lock_current())

    def test_synthetic_postgres_requires_loopback_access(self):
        with patch.object(env, "container_compatible", side_effect=lambda c: c == env.CONTAINERS["postgres"]), \
             patch.object(env, "docker", return_value=(0, "t\n")), \
             patch.object(env.socket, "create_connection", side_effect=ConnectionRefusedError):
            self.assertFalse(env.service_status()["postgres_synthetic"])

    def test_npm_source_has_no_install_hook_and_exact_versions(self):
        package = json.loads((BASE / "package.json").read_text())
        self.assertTrue(package["private"])
        self.assertNotIn("scripts", package)
        lock = json.loads((BASE / "package-lock.json").read_text())
        for name, version in package["devDependencies"].items():
            self.assertRegex(version, r"^[0-9]+\.[0-9]+\.[0-9]+(?:-(?:[0-9]+|revision[0-9]+))?$")
            self.assertEqual(lock["packages"]["node_modules/" + name]["version"], version)
            self.assertTrue(lock["packages"]["node_modules/" + name]["integrity"].startswith("sha512-"))


if __name__ == "__main__":
    unittest.main()
