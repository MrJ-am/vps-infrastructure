"""Synthetic interrupted transactions; no production target or service call."""
import os
from pathlib import Path
import tempfile
import unittest
from cutover import Checkpoint, Phase, Refused
from recovery import recover_before_opening, PRE_SNAPSHOT, RESTORABLE


class Backend:
    def __init__(self, fail=None):
        self.calls = []
        self.fail = fail

    def __getattr__(self, name):
        def operation():
            self.calls.append(name)
            if name == self.fail:
                raise RuntimeError("SYNTHETIC_PRIVATE_ERROR")
        return operation


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.checkpoint = Checkpoint(self.directory.name, uid=os.getuid())

    def test_ambiguous_or_completed_opening_never_touches_state(self):
        for phase in (Phase.OPENING, Phase.OPEN, Phase.HELD, Phase.RETURNED):
            self.checkpoint.write(phase, 123)
            backend = Backend()
            with self.assertRaisesRegex(Refused, "NOT_AUTOMATICALLY_RESTORABLE"):
                recover_before_opening(backend, self.checkpoint)
            self.assertEqual(backend.calls, [])
            self.assertEqual(self.checkpoint.read(), phase)

    def test_old_application_state_is_not_replaced_before_snapshot_checkpoint(self):
        for phase in PRE_SNAPSHOT:
            self.checkpoint.write(phase, 123)
            backend = Backend()
            result = recover_before_opening(backend, self.checkpoint)
            self.assertEqual(result["phase"], Phase.RETURNED)
            self.assertNotIn("restore_snapshot", backend.calls)
            self.assertIn("verify_adoption_not_started", backend.calls)
            self.assertLess(backend.calls.index("verify_quiescent"), backend.calls.index("restore_previous_generation"))

    def test_post_snapshot_recovery_requires_verified_pair_before_previous_boot(self):
        for phase in RESTORABLE:
            self.checkpoint.write(phase, 123)
            backend = Backend()
            recover_before_opening(backend, self.checkpoint)
            self.assertLess(backend.calls.index("verify_snapshot"), backend.calls.index("restore_snapshot"))
            self.assertLess(backend.calls.index("restore_snapshot"), backend.calls.index("restore_previous_generation"))
            self.assertLess(backend.calls.index("verify_previous_private_services"), backend.calls.index("reopen_previous_services"))

    def test_integrity_or_restore_failure_never_reopens(self):
        for failure in ("verify_snapshot", "restore_snapshot", "verify_previous_private_services"):
            self.checkpoint.write(Phase.RETURNING, 123)
            backend = Backend(failure)
            with self.assertRaisesRegex(Refused, "HELD_FOR_RECOVERY"):
                recover_before_opening(backend, self.checkpoint)
            self.assertNotIn("reopen_previous_services", backend.calls)
            self.assertEqual(self.checkpoint.read(), Phase.HELD)

    def test_release_mismatch_refuses_before_freeze_or_checkpoint_change(self):
        self.checkpoint.write(Phase.CANDIDATE, 123)
        backend = Backend("preflight_recovery")
        with self.assertRaises(RuntimeError):
            recover_before_opening(backend, self.checkpoint)
        self.assertEqual(backend.calls, ["preflight_recovery"])
        self.assertEqual(self.checkpoint.read(), Phase.CANDIDATE)

    def test_recovered_old_writes_follow_durable_returned_boundary(self):
        self.checkpoint.write(Phase.CANDIDATE,123)
        backend=Backend()
        backend.reopen_previous_services=lambda: self.assertEqual(self.checkpoint.read(),Phase.RETURNED)
        recover_before_opening(backend,self.checkpoint)

    def test_malformed_checkpoint_cannot_enter_recovery(self):
        self.checkpoint.write(Phase.CANDIDATE, 1)
        for raw in ('{"schema_version":1,"phase":"prepared","phase":"public-writes-open","elapsed_seconds":1}',
                    '{"schema_version":true,"phase":"prepared","elapsed_seconds":1}',
                    '{"schema_version":1,"phase":"prepared","elapsed_seconds":-1}'):
            Path(self.directory.name,"phase.json").write_text(raw)
            backend = Backend()
            with self.assertRaises(Refused):
                recover_before_opening(backend, self.checkpoint)
            self.assertEqual(backend.calls, [])


if __name__ == "__main__":
    unittest.main()
