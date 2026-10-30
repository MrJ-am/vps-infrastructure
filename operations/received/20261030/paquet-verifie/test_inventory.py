"""Synthetic-only tests. No real system service or production host is probed."""

import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import inventory


MARKER = "SYNTHETIC_PRIVATE_MARKER_DO_NOT_EMIT"


class InventoryTests(unittest.TestCase):
    def test_cli_has_no_generic_operation(self):
        for arguments in (["--help"], ["run", MARKER], ["--file", "/etc/shadow"], ["sql", MARKER]):
            with self.subTest(arguments=arguments), mock.patch.object(sys, "argv", ["inventory.py", *arguments]):
                output = io.StringIO()
                with contextlib.redirect_stdout(output), mock.patch.object(inventory, "collect") as collect:
                    self.assertEqual(inventory.main(), 2)
                collect.assert_not_called()
                self.assertEqual(json.loads(output.getvalue()), {"schema_version": 1, "status": "error", "code": "UNSUPPORTED_ARGUMENTS"})
                self.assertNotIn(MARKER, output.getvalue())

    def test_rejects_unlisted_commands_before_process_start(self):
        for command in [("sh", ("-c", MARKER)), ("systemctl", ("status", "nginx")), ("systemctl", ("show", "--property=Environment", "nginx")), ("forgejo", ("admin", "user", "list"))]:
            with self.subTest(command=command), mock.patch.object(inventory.subprocess, "Popen") as popen:
                self.assertEqual(inventory._fixed_command(*command), (None, "UNTRUSTED_EXECUTABLE"))
                popen.assert_not_called()

    def test_service_stdout_is_closed_enum_not_free_text(self):
        good = b"LoadState=loaded\nActiveState=active\n"
        self.assertEqual(inventory.service_result(good, None), {"status": "ok", "load_state": "loaded", "active_state": "active"})
        for raw in [good + MARKER.encode(), MARKER.encode(), good.replace(b"active", MARKER.encode()), b"LoadState=loaded\nActiveState=active\nEnvironment=SECRET\n", b"ActiveState=active\nActiveState=active\n"]:
            with self.subTest(raw=raw):
                result = inventory.service_result(raw, None)
                self.assertEqual(result, {"status": "unknown", "code": "INVALID_OUTPUT"})
                self.assertNotIn(MARKER, json.dumps(result))

    def test_absent_unit_is_not_mistaken_for_stopped_installed_service(self):
        result = inventory.service_result(b"LoadState=not-found\nActiveState=inactive\n", None)
        self.assertEqual(result["load_state"], "not-found")

    def test_version_output_is_numeric_only_even_with_suffix_marker(self):
        probe = inventory.VERSION_PROBES["forgejo"]
        result = inventory.version_result(probe, b"Forgejo version 12.0.3 built with " + MARKER.encode(), None)
        self.assertEqual(result, {"status": "ok", "release_core": [12, 0, 3], "exact_build": "not_reported"})
        self.assertNotIn(MARKER, json.dumps(result))
        for raw in [MARKER.encode(), b"Forgejo version " + MARKER.encode(), b"Forgejo version 123456789.2.3", b"Forgejo version 1.2.3" + MARKER.encode()]:
            self.assertEqual(inventory.version_result(probe, raw, None)["status"], "unknown")

    def test_exception_messages_are_never_printed(self):
        with mock.patch.object(sys, "argv", ["inventory.py"]), mock.patch.object(inventory, "collect", side_effect=RuntimeError(MARKER)):
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                self.assertEqual(inventory.main(), 1)
            self.assertNotIn(MARKER, stdout.getvalue() + stderr.getvalue())
            self.assertEqual(json.loads(stdout.getvalue())["code"], "INTERNAL_ERROR")

    def test_no_environment_inheritance_and_stderr_is_discarded(self):
        # Launch a trusted-for-test interpreter with an injected, synthetic argv;
        # production selection still accepts only the fixed table.
        real_popen = subprocess.Popen
        seen = {}

        def fake_program(argv, **kwargs):
            seen.update(kwargs)
            code = "import sys; sys.stderr.write('" + MARKER + "'); print('Forgejo version 12.0.3')"
            return real_popen([sys.executable, "-I", "-S", "-c", code], **kwargs)

        with mock.patch.object(inventory, "trusted_executable", return_value=(sys.executable, None)), mock.patch.object(inventory.subprocess, "Popen", side_effect=fake_program):
            raw, error = inventory._fixed_command("forgejo", ("--version",))
        self.assertIsNone(error)
        self.assertNotIn(MARKER.encode(), raw)
        self.assertEqual(seen["stderr"], subprocess.DEVNULL)
        self.assertEqual(seen["stdin"], subprocess.DEVNULL)
        self.assertFalse(seen["shell"])
        self.assertEqual(set(seen["env"]), {"PATH", "LANG", "LC_ALL", "SYSTEMD_COLORS", "SYSTEMD_PAGER"})

    def test_hung_and_excessive_outputs_are_bounded(self):
        real_popen = subprocess.Popen
        for code, expected in [("import time; time.sleep(10)", "TIMEOUT"), ("print('X' * 3000)", "OUTPUT_LIMIT"), ("import sys; print('" + MARKER + "'); sys.exit(1)", "COMMAND_FAILED")]:
            def fake_program(argv, **kwargs):
                return real_popen([sys.executable, "-I", "-S", "-c", code], **kwargs)
            with self.subTest(expected=expected), mock.patch.object(inventory, "COMMAND_TIMEOUT_SECONDS", 0.15), mock.patch.object(inventory, "trusted_executable", return_value=(sys.executable, None)), mock.patch.object(inventory.subprocess, "Popen", side_effect=fake_program):
                self.assertEqual(inventory._fixed_command("forgejo", ("--version",)), (None, expected))

    def test_untrusted_path_and_program_rejected(self):
        self.assertEqual(inventory.trusted_executable("../../bin/sh"), (None, "UNTRUSTED_EXECUTABLE"))
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(inventory, "BIN", Path(directory)):
            executable = Path(directory) / "forgejo"
            executable.write_text("#!/bin/sh\nexit 0\n")
            executable.chmod(0o755)
            self.assertEqual(inventory.trusted_executable("forgejo"), (None, "UNTRUSTED_EXECUTABLE"))

    def test_numeric_values_and_errors_cannot_emit_text(self):
        for value in [True, -1, 1 << 64, MARKER, {"private": MARKER}]:
            self.assertEqual(inventory.numeric(value), {"status": "unknown", "code": "INVALID_OUTPUT"})
        self.assertEqual(inventory.failure(MARKER), {"status": "unknown", "code": "INTERNAL_ERROR"})
        self.assertEqual(inventory.fixed_kernel_flag(Path("/etc/shadow")), {"status": "unknown", "code": "UNAVAILABLE"})

    def test_full_report_uses_only_declared_keys_with_synthetic_probes(self):
        disk = mock.Mock(f_blocks=1024, f_frsize=4096, f_bavail=512)
        kernel = {"status": "ok", "enabled": True}
        with mock.patch.object(inventory.os, "cpu_count", return_value=4), mock.patch.object(inventory.os, "sysconf", return_value=4096), mock.patch.object(inventory.os, "statvfs", return_value=disk), mock.patch.object(inventory, "fixed_kernel_flag", return_value=kernel), mock.patch.object(inventory.Path, "stat", side_effect=FileNotFoundError(MARKER)), mock.patch.object(inventory, "_fixed_command", return_value=(None, "UNAVAILABLE")):
            report = inventory.collect()
        schema = json.loads(Path(__file__).with_name("inventory.schema.json").read_text())
        report_schema = schema["oneOf"][0]
        self.assertEqual(set(report), set(report_schema["required"]))
        for section in ["resources", "isolation", "versions", "services"]:
            self.assertEqual(set(report[section]), set(report_schema["properties"][section]["required"]))
        self.assertNotIn(MARKER, json.dumps(report))
        self.assertEqual(report["resources"]["root_filesystem_available_bytes"]["value"], 2097152)


if __name__ == "__main__":
    unittest.main()
