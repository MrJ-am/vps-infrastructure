"""Tests synthétiques de la remise. Aucun appel SSH/SCP ni sonde réelle.

Les transports sont remplacés par des doubles ; les essais Bash locaux
remplacent l'appel de la sonde par un producteur de JSON fabriqué.
"""

import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import remise_inventaire as remise


BASE = Path(__file__).resolve().parent
FILES = remise.verify_package(BASE)
MARKER = "SYNTHETIC_DIAGNOSTIC_NEVER_TO_BE_RETURNED"
DIRECTORY = ".mrjam-inventaire-" + "a" * 32
BASH = "/run/current-system/sw/bin/bash"


def synthetic_report():
    result = {"schema_version": 1, "scope": "local_read_only_metadata",
              "authority": "unverified_observation"}
    sections = {
        "resources": ("logical_cpu_count", "memory_total_bytes",
                      "root_filesystem_total_bytes", "root_filesystem_available_bytes"),
        "isolation": ("kvm", "user_namespace_limit_nonzero", "unprivileged_user_namespace_switch"),
        "versions": ("nixos", "nix", "forgejo", "forgejo_runner", "postgresql", "kanidm"),
        "services": ("forgejo", "postgresql", "kanidm", "nginx", "mrjam_metier", "nextcloud_php_pool"),
    }
    for section, keys in sections.items():
        result[section] = {key: {"status": "unknown", "code": "UNAVAILABLE"} for key in keys}
    return result


class RemiseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="test-remise-synthetique-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        shutil.copyfile(BASE / remise.ARCHIVE, self.base / remise.ARCHIVE)
        package = self.base / "paquet-verifie"
        package.mkdir()
        for name, data in FILES.items():
            (package / name).write_bytes(data)

    def invoke(self, args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = remise.main(args, self.base)
        self.assertEqual(err.getvalue(), "")
        self.assertNotIn(MARKER, out.getvalue())
        return code, json.loads(out.getvalue())

    def test_verify_only_is_local(self):
        with mock.patch.object(remise, "quiet_run") as transport:
            self.assertEqual(self.invoke(["--verify-only"]),
                             (0, {"status": "ok", "code": "PACKAGE_VERIFIED"}))
        transport.assert_not_called()

    def test_missing_root_and_invalid_account_never_connect(self):
        for args in ([], ["root"], ["0"], ["root@vps"], ["x;sh"], ["--help"], ["a", "b"]):
            with self.subTest(args=args), mock.patch.object(remise, "quiet_run") as transport:
                self.assertEqual(self.invoke(args)[0], 1)
                transport.assert_not_called()

    def test_archive_tampering_fails_before_transport(self):
        with (self.base / remise.ARCHIVE).open("ab") as handle:
            handle.write(b"changed")
        with mock.patch.object(remise, "quiet_run") as transport:
            self.assertEqual(self.invoke(["synthetic"])[1]["code"], "PACKAGE_INTEGRITY_FAILED")
        transport.assert_not_called()

    def test_changed_file_and_updated_manifest_do_not_bypass_archive(self):
        import hashlib
        package = self.base / "paquet-verifie"
        original = FILES["inventory.py"]
        changed = original + b"\n# changed\n"
        (package / "inventory.py").write_bytes(changed)
        sums = FILES["SHA256SUMS"].replace(hashlib.sha256(original).hexdigest().encode(),
                                         hashlib.sha256(changed).hexdigest().encode())
        (package / "SHA256SUMS").write_bytes(sums)
        with mock.patch.object(remise, "quiet_run") as transport:
            self.assertEqual(self.invoke(["synthetic"])[1]["code"], "PACKAGE_INTEGRITY_FAILED")
        transport.assert_not_called()

    def test_symlink_member_is_rejected(self):
        target = self.base / "paquet-verifie/inventory.py"
        target.unlink()
        target.symlink_to(BASE / "paquet-verifie/inventory.py")
        self.assertEqual(self.invoke(["--verify-only"])[1]["code"], "PACKAGE_INTEGRITY_FAILED")

    def fake_transport(self, calls, *, fail_at=None, status=1, content=None):
        def run(argv, **kwargs):
            calls.append((argv, kwargs))
            if len(calls) == fail_at:
                return status
            if argv[0] == remise.SCP and argv[-2].startswith("vps:"):
                Path(argv[-1]).write_bytes(content if content is not None
                                          else json.dumps(synthetic_report()).encode())
            return 0
        return run

    def test_success_only_uploads_three_files_and_publishes_validated_json(self):
        calls = []
        with mock.patch.object(remise, "quiet_run", side_effect=self.fake_transport(calls)):
            self.assertEqual(self.invoke(["synthetic"]),
                             (0, {"status": "ok", "code": "REPORT_VALIDATED"}))
        self.assertEqual([argv[0] for argv, _ in calls], [remise.SSH, remise.SCP, remise.SSH, remise.SCP])
        upload = calls[1][0]
        self.assertEqual([Path(p).name for p in upload[-4:-1]], list(remise.RUNTIME))
        self.assertEqual(calls[3][0][-2].split("/")[-1], remise.OUTPUT)
        self.assertTrue(calls[3][1]["limit_file"])
        for argv, _ in calls:
            self.assertIn("User=synthetic", argv)
            self.assertIn("StrictHostKeyChecking=yes", argv)
            self.assertIn("BatchMode=yes", argv)
            self.assertNotIn("User=root", argv)
        result = self.base / remise.OUTPUT
        self.assertEqual(json.loads(result.read_bytes()), synthetic_report())
        self.assertEqual(result.stat().st_mode & 0o777, 0o600)

    def test_each_transport_failure_stops_and_never_publishes(self):
        cases = ((1, 255, "SSH_PREPARATION_FAILED"),
                 (1, 41, "EXISTING_NONPRIVILEGED_ACCOUNT_REQUIRED"),
                 (1, 42, "REMOTE_PYTHON_311_REQUIRED"),
                 (1, 43, "REMOTE_WORK_DIRECTORY_UNAVAILABLE"),
                 (2, 1, "UPLOAD_FAILED"), (3, 44, "REMOTE_INTEGRITY_FAILED"),
                 (3, 45, "REMOTE_PIPELINE_FAILED"), (4, 1, "DOWNLOAD_FAILED"))
        for step, status, expected in cases:
            calls = []
            with self.subTest(step=step, status=status), mock.patch.object(
                remise, "quiet_run", side_effect=self.fake_transport(calls, fail_at=step, status=status)
            ):
                self.assertEqual(self.invoke(["synthetic"]), (1, {"status": "failed", "code": expected}))
                self.assertEqual(len(calls), step)
                self.assertFalse((self.base / remise.OUTPUT).exists())

    def test_invalid_and_oversized_return_never_published_or_echoed(self):
        for raw in (MARKER.encode(), b"x" * (remise.MAX_REPORT + 1),
                    b'{"schema_version":1,"status":"error","code":"INTERNAL_ERROR"}'):
            with self.subTest(size=len(raw)), mock.patch.object(
                remise, "quiet_run", side_effect=self.fake_transport([], content=raw)
            ):
                self.assertEqual(self.invoke(["synthetic"])[1]["code"], "LOCAL_REPORT_REJECTED")
                self.assertFalse((self.base / remise.OUTPUT).exists())

    def test_previous_report_is_never_overwritten(self):
        previous = self.base / remise.OUTPUT
        previous.write_bytes(b"previous synthetic fixture")
        with mock.patch.object(remise, "quiet_run") as transport:
            self.assertEqual(self.invoke(["synthetic"])[1]["code"], "RESULT_ALREADY_EXISTS")
        transport.assert_not_called()
        self.assertEqual(previous.read_bytes(), b"previous synthetic fixture")

    def test_diagnostics_are_discarded_at_transport_boundary(self):
        result = subprocess.CompletedProcess([], 255, stdout=MARKER, stderr=MARKER)
        with mock.patch.object(remise.subprocess, "run", return_value=result) as run:
            self.assertEqual(remise.quiet_run([remise.SSH], body=b"synthetic"), 255)
        self.assertIs(run.call_args.kwargs["stdout"], subprocess.DEVNULL)
        self.assertIs(run.call_args.kwargs["stderr"], subprocess.DEVNULL)

    def test_timeout_is_a_closed_code(self):
        with mock.patch.object(remise.subprocess, "run", side_effect=subprocess.TimeoutExpired(MARKER, 90)):
            with self.assertRaises(remise.ClosedFailure) as ctx:
                remise.quiet_run([remise.SSH])
        self.assertEqual(ctx.exception.code, "TRANSPORT_TIMEOUT")

    def run_synthetic_bash(self, payload, *, probe_status=0, python_missing=False, tamper=False):
        with tempfile.TemporaryDirectory(prefix="bash-synthetique-") as temp:
            root = Path(temp)
            directory = root / DIRECTORY
            directory.mkdir()
            for name in remise.RUNTIME:
                (directory / name).write_bytes(FILES[name])
            if tamper:
                (directory / "inventory.py").write_bytes(b"synthetic changed bytes")
            fake_bin = root / "bin"
            fake_bin.mkdir()
            wrapper = fake_bin / "python3"
            if python_missing:
                code = "exit 1\n"
            else:
                code = ("if [[ \"${3-}\" == ./inventory.py ]]; then\n"
                        + "  printf '%s\\n' '" + payload + "'\n"
                        + f"  exit {probe_status}\nfi\n"
                        + f"exec '{sys.executable}' \"$@\"\n")
            wrapper.write_text(f"#!{BASH}\n" + code)
            wrapper.chmod(0o700)
            environment = dict(os.environ)
            environment["PATH"] = str(fake_bin) + ":/run/current-system/sw/bin"
            # No HOME change, no SSH, no real inventory invocation.
            result = subprocess.run([BASH, "--noprofile", "--norc", "-s"],
                                    input=remise.remote_inventory(DIRECTORY, FILES),
                                    cwd=root, env=environment, capture_output=True, timeout=10)
            self.assertEqual(result.stdout, b"")
            self.assertEqual(result.stderr, b"")
            return result.returncode

    def test_real_bash_pipefail_blocks_probe_failure_even_with_valid_json(self):
        self.assertEqual(self.run_synthetic_bash(json.dumps(synthetic_report()), probe_status=7), 45)

    def test_real_bash_pipefail_blocks_filter_rejection(self):
        self.assertEqual(self.run_synthetic_bash(MARKER), 45)

    def test_real_bash_accepts_only_successful_synthetic_pipeline(self):
        self.assertEqual(self.run_synthetic_bash(json.dumps(synthetic_report())), 0)

    def test_real_bash_identifies_python_precondition(self):
        self.assertEqual(self.run_synthetic_bash("", python_missing=True), 42)

    def test_real_bash_rechecks_transferred_hashes(self):
        self.assertEqual(self.run_synthetic_bash("", tamper=True), 44)


if __name__ == "__main__":
    unittest.main()
