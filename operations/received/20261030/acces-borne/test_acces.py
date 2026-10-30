"""Tests synthétiques : aucune connexion ni création de compte réel."""
import base64
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import installer
import runner
import acces_borne as access


FILES = access.remise.verify_package(access.PACKAGE)
PAYLOAD = runner.MAGIC + b"".join(FILES[name] for name, _, _ in runner.RUNTIME)
POLICY = """pubkeyauthentication yes
usepam yes
authorizedkeyscommand none
trustedusercakeys none
forcecommand none
chrootdirectory none
authenticationmethods any
authorizedkeysfile .ssh/authorized_keys /etc/ssh/authorized_keys.d/%u
acceptenv LANG
acceptenv LC_*
"""


class AccessTests(unittest.TestCase):
    def test_payload_requires_exact_verified_three_files(self):
        self.assertEqual(runner.unpack(PAYLOAD), {name: FILES[name] for name, _, _ in runner.RUNTIME})
        for data in (b"", PAYLOAD + b"x", PAYLOAD[:-1], PAYLOAD.replace(b"import", b"Import", 1)):
            with self.subTest(size=len(data)), self.assertRaises(ValueError):
                runner.unpack(data)

    def test_policy_rejects_alternative_auth_and_group_requirements(self):
        self.assertTrue(installer.ssh_policy_allowed(POLICY))
        variant = "\n".join("  " + line.split(" ", 1)[0].upper() + "\t" + line.split(" ", 1)[1]
                            for line in POLICY.splitlines())
        self.assertTrue(installer.ssh_policy_allowed(variant))
        changes = (("authorizedkeyscommand none", "authorizedkeyscommand /external"),
                   ("trustedusercakeys none", "trustedusercakeys /ca"),
                   ("forcecommand none", "forcecommand /generic"),
                   ("chrootdirectory none", "chrootdirectory /other"),
                   ("usepam yes", "usepam no"),
                   ("authenticationmethods any", "authenticationmethods publickey,password"),
                   ("acceptenv LANG", "acceptenv *"),
                   (".ssh/authorized_keys", "/other"))
        for before, after in changes:
            self.assertFalse(installer.ssh_policy_allowed(POLICY.replace(before, after)))
        for extra in ("allowusers root\n", "allowgroups wheel\n", "denyusers mrjam-*\n"):
            self.assertFalse(installer.ssh_policy_allowed(POLICY + extra))

    def test_public_key_is_only_the_expected_public_format(self):
        key = "ssh-ed25519 " + base64.b64encode(b"\0\0\0\x0bssh-ed25519\0\0\0\x20" + b"x" * 32).decode() + " mrjam-inventory-borne-20261030"
        self.assertTrue(installer.public_key_allowed(key))
        for value in (key + "\ncommand=evil", "private secret", key.replace("ed25519", "rsa", 1)):
            self.assertFalse(installer.public_key_allowed(value))

    def test_login_rejects_free_shell_and_arbitrary_commands(self):
        with tempfile.TemporaryDirectory() as temp:
            login = Path(temp) / "login"
            login.write_text(installer.login_source("/unused/python3"))
            login.chmod(0o700)
            for args, original in (([], ""), (["-c", "id"], "id"),
                                   (["-c", installer.OPERATION], "id")):
                environment = dict(os.environ)
                environment["SSH_ORIGINAL_COMMAND"] = original
                result = subprocess.run([str(login), *args], env=environment, capture_output=True, timeout=5)
                self.assertEqual(result.returncode, 64)
                self.assertEqual(result.stdout + result.stderr, b"")

    def test_login_ignores_bash_env(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            marker = root / "unexpected"
            env_script = root / "startup"
            env_script.write_text(f"touch '{marker}'\n")
            login = root / "login"
            login.write_text(installer.login_source("/unused/python3"))
            login.chmod(0o700)
            environment = dict(os.environ)
            environment["BASH_ENV"] = str(env_script)
            result = subprocess.run([str(login)], env=environment, capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 64)
            self.assertFalse(marker.exists())

    def test_root_is_refused_by_runner(self):
        with mock.patch.object(runner.sys, "argv", ["runner.py"]), mock.patch.object(runner.os, "getuid", return_value=0):
            self.assertEqual(runner.main(), 64)

    def test_invalid_payload_never_starts_probe(self):
        incoming = mock.Mock(buffer=io.BytesIO(b"INVALID"))
        with mock.patch.object(runner.sys, "argv", ["runner.py"]), mock.patch.object(runner.sys, "stdin", incoming), mock.patch.object(runner.subprocess, "run") as run:
            self.assertEqual(runner.main(), 65)
        run.assert_not_called()

    def test_pipeline_failure_does_not_read_or_return_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "work").mkdir()
            incoming = mock.Mock(buffer=io.BytesIO(PAYLOAD))
            outgoing = mock.Mock(buffer=io.BytesIO())
            result = subprocess.CompletedProcess([], 1)
            with mock.patch.object(runner, "ROOT", root), mock.patch.object(runner.sys, "argv", ["runner.py"]), mock.patch.object(runner.sys, "stdin", incoming), mock.patch.object(runner.sys, "stdout", outgoing), mock.patch.object(runner.subprocess, "run", return_value=result):
                self.assertEqual(runner.main(), 67)
                self.assertEqual(outgoing.buffer.getvalue(), b"")

    def test_rejected_local_report_is_not_published(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "frontiere-verifiee").write_text("synthetic")
            with mock.patch.object(access, "BASE", root), mock.patch.object(access, "PACKAGE", root), mock.patch.object(access, "bounded_call", return_value=(0, 7, b"INVALID")):
                with self.assertRaises(access.remise.ClosedFailure) as failure:
                    access.collect(FILES)
                self.assertEqual(failure.exception.code, "LOCAL_REPORT_REJECTED")
                self.assertFalse((root / access.remise.OUTPUT).exists())

    def test_remote_failure_prevents_local_validation_and_publication(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "frontiere-verifiee").write_text("synthetic")
            with mock.patch.object(access, "BASE", root), mock.patch.object(access, "PACKAGE", root), mock.patch.object(access, "bounded_call", return_value=(67, 0, b"")), mock.patch.object(access.subprocess, "run") as run:
                with self.assertRaises(access.remise.ClosedFailure) as failure:
                    access.collect(FILES)
                self.assertEqual(failure.exception.code, "REMOTE_PIPELINE_FAILED")
                run.assert_not_called()
                self.assertFalse((root / access.remise.OUTPUT).exists())


if __name__ == "__main__":
    unittest.main()
