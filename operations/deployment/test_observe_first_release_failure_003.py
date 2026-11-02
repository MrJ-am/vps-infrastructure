"""Real synthetic files; never read the production state directory."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).with_name("observe-first-release-failure-003-20261102.py")
spec = importlib.util.spec_from_file_location("failure_probe", SOURCE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
PRIVATE = "DO_NOT_EXPORT_SYNTHETIC_PRIVATE_MARKER"


class Probe(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = m.load_contract()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=Path(".local").resolve())
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.enterContext(patch.object(m, "STATE", self.directory))
        self.enterContext(patch.object(m, "OWNER", (os.getuid(), os.getgid())))

    def failure(self):
        return {"schema_version": 1, "release_sha256": m.RELEASE_SHA256,
                "step": "systemd-start", "component": "mrjam-vision-closure.service",
                "code": "SYSTEM_OPERATION_REFUSED"}

    def phase(self):
        return {"schema_version": 1, "phase": self.contract.Phase.RETURNED.value,
                "elapsed_seconds": 42}

    def write(self, name, value):
        path = self.directory / name
        raw = value if type(value) is bytes else json.dumps(value).encode()
        path.write_bytes(raw)
        path.chmod(0o600)
        return path

    def test_absence_is_not_a_failure_or_success_claim(self):
        result = m.observe(self.contract)
        self.assertFalse(result["failure_present"])
        self.assertIsNone(result["failure"])
        self.assertEqual(result["phase"], "absent")
        self.assertNotIn("deployment_verified", result)
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_exact_record_and_checkpoint_read_without_changes(self):
        paths = [self.write("failure.json", self.failure()), self.write("phase.json", self.phase())]
        before = {p: (p.read_bytes(), m.fingerprint(p.stat())) for p in paths}
        self.assertEqual(m.observe(self.contract)["failure"], self.failure())
        self.assertEqual(m.observe(self.contract)["phase"], self.phase()["phase"])
        self.assertEqual(before, {p: (p.read_bytes(), m.fingerprint(p.stat())) for p in paths})

    def test_foreign_release_unknown_fields_and_literals_refused(self):
        variants = [{**self.failure(), "release_sha256": "a" * 64},
                    {**self.failure(), "schema_version": True},
                    {**self.failure(), "extra": PRIVATE},
                    {**self.failure(), "step": PRIVATE},
                    {**self.failure(), "component": PRIVATE},
                    {**self.failure(), "code": PRIVATE},
                    {**self.failure(), "code": []}]
        for value in variants:
            with self.subTest(value_type=type(value).__name__):
                self.write("failure.json", value)
                with self.assertRaises(m.Refused):
                    m.observe(self.contract)

    def test_null_duplicate_invalid_oversized_and_nonfinite_json_refused(self):
        variants = [b"null", b"[]", b"", b"{", b"x" * 1025,
                    b'{"schema_version":1,"schema_version":1}',
                    b'{"schema_version":NaN}', b'"' + PRIVATE.encode() + b'"']
        for raw in variants:
            self.write("failure.json", raw)
            with self.assertRaises((m.Refused, self.contract.Refused)):
                m.observe(self.contract)

    def test_checkpoint_schema_refused_even_without_failure(self):
        for value in ({**self.phase(), "phase": PRIVATE},
                      {**self.phase(), "elapsed_seconds": True},
                      {**self.phase(), "elapsed_seconds": -1},
                      {**self.phase(), "schema_version": True},
                      {**self.phase(), "extra": PRIVATE}, None):
            self.write("phase.json", value)
            with self.assertRaises(m.Refused):
                m.observe(self.contract)

    def test_symlink_hardlink_mode_and_fifo_refused_before_content_read(self):
        target = self.write("private-never-read", PRIVATE.encode())
        path = self.directory / "failure.json"
        path.symlink_to(target)
        with self.assertRaises(OSError):
            m.observe(self.contract)
        path.unlink()
        os.link(target, path)
        with self.assertRaises(m.Refused):
            m.observe(self.contract)
        path.unlink()
        self.write("failure.json", self.failure()).chmod(0o640)
        with self.assertRaises(m.Refused):
            m.observe(self.contract)
        path.unlink()
        os.mkfifo(path, 0o600)
        with self.assertRaises(m.Refused):
            m.observe(self.contract)

    def test_pending_failure_is_never_opened(self):
        self.write("failure.json.next", PRIVATE.encode())
        output = m.observe(self.contract)
        self.assertFalse(output["failure_present"])
        self.assertNotIn(PRIVATE, json.dumps(output))

    def test_directory_symlink_and_wrong_mode_refused(self):
        sibling = self.directory / "sibling"
        sibling.mkdir(mode=0o700)
        link = self.directory / "alias"
        link.symlink_to(sibling)
        with patch.object(m, "STATE", link):
            with self.assertRaises(OSError):
                m.observe(self.contract)
        self.directory.chmod(0o750)
        with self.assertRaises(m.Refused):
            m.observe(self.contract)

    def test_replacement_during_read_refuses(self):
        path = self.write("failure.json", self.failure())
        original = os.stat
        replaced = False
        def changed(name, *args, **kwargs):
            nonlocal replaced
            if name == "failure.json" and not replaced:
                replaced = True
                replacement = self.write("replacement", self.failure())
                os.replace(replacement, path)
            return original(name, *args, **kwargs)
        with patch.object(m.os, "stat", side_effect=changed):
            with self.assertRaises(m.Refused):
                m.observe(self.contract)

    def test_main_output_stays_closed_on_rejection(self):
        self.write("failure.json", {**self.failure(), "code": PRIVATE})
        output = io.StringIO()
        with patch.object(m.sys, "argv", ["probe"]), patch.object(m.os, "geteuid", return_value=0), \
             patch.object(m.os, "uname", return_value=SimpleNamespace(nodename=m.HOST)), \
             patch.object(m, "load_contract", return_value=self.contract), contextlib.redirect_stdout(output):
            self.assertEqual(m.main(), 1)
        self.assertEqual(json.loads(output.getvalue()), {
            "schema_version": 1, "code": "FIRST_RELEASE_FAILURE_OBSERVATION_REFUSED"})
        self.assertNotIn(PRIVATE, output.getvalue())

    def test_cli_arguments_refused_without_reading_state(self):
        with patch.object(m.sys, "argv", ["probe", "arbitrary"]), \
             patch.object(m, "load_contract", side_effect=AssertionError("must not load")), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(m.main(), 1)


if __name__ == "__main__":
    unittest.main()
