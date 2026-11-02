"""Closed diagnostic projection with real private files and injected processes."""
import ast
import contextlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import release_backend as m
from cutover import Checkpoint, Cutover, Phase, Refused as CutoverRefused
from test_release_backend import sealed


SECRET = "PRIVATE_UNKNOWN_UPPERCASE_TOKEN"


class UnprintableError(RuntimeError):
    def __str__(self):
        raise AssertionError("Exception text was requested")


class Observations(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.state = Path(self.directory.name)
        self.enterContext(patch.object(m, "STATE", self.state))
        self.backend = m.Backend(sealed(), clock=lambda: 100)
        self.backend.diagnostics_enabled = True
        self.backend.started = 100
        self.backend.checkpoint = SimpleNamespace(read=lambda: Phase.ADOPTED)

    def read(self):
        path = self.state / "failure.json"
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        raw = path.read_bytes()
        self.assertLess(len(raw), 1024)
        self.assertNotIn(SECRET.encode(), raw)
        value = json.loads(raw)
        self.assertEqual(set(value), {"schema_version", "release_sha256", "step", "component", "code"})
        self.assertEqual(value["release_sha256"], self.backend.release.digest)
        return value

    def test_known_failure_persists_once_without_overwriting_first_evidence(self):
        self.backend.record_failure("snapshot", "none", m.SnapshotRefused("SNAPSHOT_OPERATION_FAILED"))
        before = (self.state / "failure.json").read_bytes()
        inode = (self.state / "failure.json").stat().st_ino
        self.backend.record_failure("helper", "forgejo_governance", m.Refused("SOURCE_METADATA_NOT_CONVERGED"))
        self.assertEqual(self.read()["code"], "SNAPSHOT_OPERATION_FAILED")
        self.assertEqual((self.state / "failure.json").read_bytes(), before)
        self.assertEqual((self.state / "failure.json").stat().st_ino, inode)

    def test_unknown_uppercase_or_unprintable_errors_are_not_serialized(self):
        for error in (m.Refused(SECRET), UnprintableError(SECRET), RuntimeError("SYSTEM_OPERATION_REFUSED")):
            with self.subTest(kind=type(error).__name__):
                self.backend.failure_recorded = False
                (self.state / "failure.json").unlink(missing_ok=True)
                output = io.StringIO()
                with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                    self.backend.record_failure(SECRET, SECRET, error)
                self.assertEqual(output.getvalue(), "")
                self.assertEqual(self.read()["code"], "UNKNOWN_FAILURE")
                self.assertEqual(self.read()["step"], "backend")
                self.assertEqual(self.read()["component"], "none")

    def test_subclasses_and_non_string_arguments_are_not_trusted_codes(self):
        class Similar(m.Refused):
            pass
        class SimilarString(str):
            pass
        for error in (Similar("SYSTEM_OPERATION_REFUSED"), m.Refused(SimilarString("SYSTEM_OPERATION_REFUSED")),
                      m.Refused({"code": SECRET}), m.Refused("SYSTEM_OPERATION_REFUSED", SECRET)):
            self.backend.failure_recorded = False
            (self.state / "failure.json").unlink(missing_ok=True)
            self.backend.record_failure("backend", "none", error)
            self.assertEqual(self.read()["code"], "UNKNOWN_FAILURE")

    def test_preflight_and_noncontext_backend_never_write_diagnostic(self):
        self.backend.started = None
        self.backend.record_failure("backend", "none", m.Refused("PRIVATE_FILE_REFUSED"))
        self.backend.started = 100
        self.backend.diagnostics_enabled = False
        self.backend.record_failure("backend", "none", m.Refused("PRIVATE_FILE_REFUSED"))
        self.assertFalse((self.state / "failure.json").exists())

    def test_observation_io_failure_preserves_exception_identity(self):
        original = UnprintableError(SECRET)
        with patch.object(m, "publish_private", side_effect=OSError(SECRET)):
            with self.assertRaises(UnprintableError) as raised:
                with self.backend.failure_step("start-private-services"):
                    raise original
        self.assertIs(raised.exception, original)
        self.assertFalse((self.state / "failure.json").exists())

    def test_existing_file_and_symlink_are_not_overwritten(self):
        target = self.state / "retained"
        target.write_text("retained")
        for symlink in (False, True):
            self.backend.failure_recorded = False
            path = self.state / "failure.json"
            if symlink:
                path.symlink_to(target)
            else:
                path.write_text("retained")
            inode = path.lstat().st_ino
            self.backend.record_failure("snapshot", "none", m.Refused("SEALED_OPERATION_REFUSED"))
            self.assertEqual(path.lstat().st_ino, inode)
            self.assertEqual(path.read_text(), "retained")
            self.assertEqual(target.read_text(), "retained")
            self.assertFalse((self.state / "failure.json.next").exists())
            path.unlink()

    def test_exact_failed_start_is_preserved_before_outer_private_stage(self):
        called = []
        def run(args, **kwargs):
            called.append(tuple(args))
            self.assertEqual(kwargs["stderr"], subprocess.DEVNULL)
            failed = args[1:] == ["start", "mrjam-vision-closure.service"]
            return SimpleNamespace(returncode=1 if failed else 0, stdout=b"", stderr=SECRET.encode())
        self.backend.run = run
        self.backend.control.release_masks = lambda *_: None
        with self.assertRaises(m.SystemRefused):
            self.backend.start_private_services()
        value = self.read()
        self.assertEqual((value["step"], value["component"], value["code"]),
                         ("systemd-start", "mrjam-vision-closure.service", "SYSTEM_OPERATION_REFUSED"))
        self.assertEqual(called[-1][1:], ("start", "mrjam-vision-closure.service"))

    def test_known_closed_helper_code_is_kept_without_stdout_or_stderr(self):
        payload = b'{"schema_version":1,"code":"SOURCE_METADATA_NOT_CONVERGED"}'
        self.backend.run = lambda *_a, **_k: SimpleNamespace(returncode=1, stdout=payload, stderr=SECRET.encode())
        with self.assertRaisesRegex(m.Refused, "SOURCE_METADATA_NOT_CONVERGED"):
            self.backend.helper("forgejo_governance")
        self.assertEqual(self.read()["component"], "forgejo_governance")
        self.assertEqual(self.read()["code"], "SOURCE_METADATA_NOT_CONVERGED")

    def test_arbitrary_malformed_oversized_or_extra_helper_fields_collapse(self):
        payloads = [SECRET.encode(), b'{"schema_version":1,"code":"'+SECRET.encode()+b'"}',
            b'{"schema_version":true,"code":"SOURCE_METADATA_NOT_CONVERGED"}',
            b'{"schema_version":1,"code":"SOURCE_METADATA_NOT_CONVERGED","private":"'+SECRET.encode()+b'"}',
            b'{"schema_version":1,"code":"SOURCE_METADATA_NOT_CONVERGED","code":"'+SECRET.encode()+b'"}',
            b"x"*65537]
        for payload in payloads:
            self.backend.failure_recorded = False
            (self.state / "failure.json").unlink(missing_ok=True)
            self.backend.run = lambda *_a, **_k: SimpleNamespace(returncode=1, stdout=payload, stderr=SECRET.encode())
            with self.assertRaisesRegex(m.Refused, "UNKNOWN_FAILURE"):
                self.backend.helper("forgejo_governance")
            self.assertEqual(self.read()["code"], "UNKNOWN_FAILURE")

    def test_private_health_keeps_exact_fixed_component(self):
        self.backend.ready = lambda *_: None
        self.backend.helper = lambda *_: {"passed":True,"mutation_performed":False,"private_values_exported":False}
        self.backend.closed_status = lambda *_: 503
        with self.assertRaisesRegex(m.Refused, "FORGEJO_PRIVATE_HEALTH_REFUSED"):
            self.backend.verify_private_services()
        value = self.read()
        self.assertEqual((value["step"], value["component"]), ("http-health", "forgejo"))

    def test_all_static_internal_and_governance_literals_are_allowlisted(self):
        root = Path(__file__).parent
        paths = [root/name for name in ("release_backend.py", "cutover.py", "generation.py", "system_control.py",
                 "snapshot.py", "stage_adoption.py", "stage_credentials.py", "forgejo-governance/core.py",
                 "forgejo-governance/entry.py")] + [root.parent/"forgejo/reconcile.py"]
        for path in paths:
            for node in ast.walk(ast.parse(path.read_text())):
                if not isinstance(node, ast.Call):
                    continue
                name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else None
                if name not in ("require", "Refused", "SnapshotRefused"):
                    continue
                index = 1 if name == "require" else 0
                if len(node.args) > index and isinstance(node.args[index], ast.Constant) and type(node.args[index].value) is str:
                    self.assertIn(node.args[index].value, m.FAILURE_CODES, str(path))

    def exercise_engine(self, public, enabled):
        folder = self.state / ("engine-"+str(public)+"-"+str(enabled))
        folder.mkdir(mode=0o700)
        checkpoint = Checkpoint(folder, uid=os.getuid())
        class EngineBackend:
            failure_step = m.Backend.failure_step
            record_failure = m.Backend.record_failure
            started = 1
            failure_recorded = False
            diagnostics_enabled = enabled
            release = self.backend.release
            def __init__(self):
                self.calls = []
            def __getattr__(self, name):
                def call():
                    self.calls.append(name)
                    if name in ("restore_snapshot", "hold_current_state") and enabled:
                        assert (folder/"failure.json").exists()
                return call
            @m.observed_failure("start-private-services")
            def start_private_services(self):
                self.calls.append("start_private_services")
                if not public:
                    raise UnprintableError(SECRET)
            @m.observed_failure("verify-public-services")
            def verify_public_services(self):
                self.calls.append("verify_public_services")
                if public:
                    raise UnprintableError(SECRET)
        backend = EngineBackend()
        with patch.object(m, "STATE", folder), self.assertRaises(CutoverRefused) as raised:
            Cutover(backend, checkpoint).execute()
        if enabled:
            self.assertNotIn(SECRET, (folder/"failure.json").read_text())
        return backend.calls, raised.exception.args, checkpoint.read()

    def test_diagnostic_precedes_return_and_does_not_change_return_sequence(self):
        observed = self.exercise_engine(False, True)
        baseline = self.exercise_engine(False, False)
        self.assertEqual(observed, baseline)
        self.assertEqual(observed[2], Phase.RETURNED)

    def test_diagnostic_precedes_hold_and_never_enables_postwrite_restore(self):
        observed = self.exercise_engine(True, True)
        baseline = self.exercise_engine(True, False)
        self.assertEqual(observed, baseline)
        self.assertEqual(observed[2], Phase.HELD)
        self.assertNotIn("restore_snapshot", observed[0])


if __name__ == "__main__":
    unittest.main()
