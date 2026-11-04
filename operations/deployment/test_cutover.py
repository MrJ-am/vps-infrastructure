"""Synthetic fault injection for the first-cutover transaction engine."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("cutover", Path(__file__).with_name("cutover.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class InventedBackend:
    def __init__(self, fail=None):
        self.calls = []
        self.fail = fail
        self.failed = False

    def __getattr__(self, name):
        def operation():
            self.calls.append(name)
            if name == self.fail and not self.failed:
                self.failed = True
                raise RuntimeError("SYNTHETIC_PRIVATE_DIAGNOSTIC")
        return operation


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.checkpoint = module.Checkpoint(self.folder.name, uid=os.getuid())

    def tearDown(self):
        self.folder.cleanup()

    def test_public_writes_follow_snapshot_and_private_validation(self):
        backend = InventedBackend()
        result = module.Cutover(backend, self.checkpoint).execute()
        self.assertEqual(result["code"], "CUTOVER_VERIFIED")
        self.assertEqual(backend.calls, ["preflight", "freeze", "verify_quiescent", "snapshot",
            "verify_snapshot", "install_candidate", "adopt_private_state", "start_private_services",
            "verify_private_services", "open_public_writes", "verify_public_services"])
        self.assertEqual(self.checkpoint.read(), module.Phase.OPEN)

    def test_each_failure_before_reopening_returns_coherently(self):
        for step in ["freeze", "verify_quiescent", "snapshot", "verify_snapshot", "install_candidate",
                     "adopt_private_state", "start_private_services", "verify_private_services"]:
            with self.subTest(step=step), tempfile.TemporaryDirectory() as folder:
                checkpoint = module.Checkpoint(folder, uid=os.getuid())
                backend = InventedBackend(step)
                with self.assertRaises(module.Refused) as raised:
                    module.Cutover(backend, checkpoint).execute()
                self.assertEqual(str(raised.exception), "CUTOVER_REFUSED_PREVIOUS_GENERATION_RESTORED")
                self.assertNotIn("open_public_writes", backend.calls)
                self.assertEqual(checkpoint.read(), module.Phase.RETURNED)
                self.assertIn("restore_previous_generation", backend.calls)
                snapshot_valid = step in ("install_candidate", "adopt_private_state", "start_private_services", "verify_private_services")
                self.assertEqual("restore_snapshot" in backend.calls, snapshot_valid)
                if snapshot_valid:
                    self.assertLess(backend.calls.index("restore_snapshot"), backend.calls.index("restore_previous_generation"))

    def test_opening_failures_never_restore_old_data(self):
        for step in ["open_public_writes", "verify_public_services"]:
            with self.subTest(step=step), tempfile.TemporaryDirectory() as folder:
                backend = InventedBackend(step)
                checkpoint = module.Checkpoint(folder, uid=os.getuid())
                with self.assertRaises(module.Refused) as raised:
                    module.Cutover(backend, checkpoint).execute()
                self.assertEqual(str(raised.exception), "OPENING_FAILED_CURRENT_STATE_PRESERVED")
                self.assertNotIn("restore_snapshot", backend.calls)
                self.assertNotIn("restore_previous_generation", backend.calls)
                self.assertEqual(backend.calls[-1], "hold_current_state")
                self.assertEqual(checkpoint.read(), module.Phase.HELD)

    def test_persisted_checkpoint_precedes_the_first_new_public_write(self):
        backend = InventedBackend()
        def open_public_writes():
            self.assertEqual(self.checkpoint.read(), module.Phase.OPENING)
        backend.open_public_writes = open_public_writes
        module.Cutover(backend, self.checkpoint).execute()

    def test_replay_of_existing_transaction_refused_before_any_mutation(self):
        for phase in module.Phase:
            self.checkpoint.write(phase, 40)
            backend = InventedBackend()
            with self.assertRaisesRegex(module.Refused, "EXISTING_TRANSACTION_REQUIRES_RECOVERY"):
                module.Cutover(backend, self.checkpoint).execute()
            self.assertEqual(backend.calls, [])

    def test_new_instance_cannot_restore_after_durable_reopening(self):
        for phase in (module.Phase.OPENING,module.Phase.OPEN,module.Phase.HELD,module.Phase.RETURNED):
            self.checkpoint.write(phase, 40)
            backend = InventedBackend()
            with self.assertRaisesRegex(module.Refused, "RESTORE_AFTER_PUBLIC_WRITES_REFUSED"):
                module.Cutover(backend, self.checkpoint).return_before_opening()
            self.assertEqual(backend.calls, [])

    def test_returned_boundary_is_durable_before_old_boot_or_writes_reopen(self):
        backend=InventedBackend('verify_private_services')
        def reopen():
            self.assertEqual(self.checkpoint.read(),module.Phase.RETURNED)
        backend.reopen_previous_services=reopen
        subject=module.Cutover(backend,self.checkpoint)
        with self.assertRaisesRegex(module.Refused,'PREVIOUS_GENERATION_RESTORED'):
            subject.execute()
        with self.assertRaisesRegex(module.Refused,'RESTORE_AFTER_PUBLIC_WRITES_REFUSED'):
            subject.return_before_opening()

    def test_return_margin_exhaustion_returns_before_candidate_install(self):
        times = iter([0, 0, 1, 5401, 5402, 5403])
        backend = InventedBackend()
        with self.assertRaises(module.Refused):
            module.Cutover(backend, self.checkpoint, clock=lambda: next(times)).execute()
        self.assertNotIn("install_candidate", backend.calls)
        self.assertIn("restore_previous_generation", backend.calls)

    def test_new_instance_cannot_restore_preopening_without_recovery(self):
        for phase in (module.Phase.FREEZING, module.Phase.FROZEN, module.Phase.SNAPSHOT,
                      module.Phase.CANDIDATE, module.Phase.ADOPTED, module.Phase.VERIFIED):
            self.checkpoint.write(phase, 40)
            backend = InventedBackend()
            with self.assertRaisesRegex(module.Refused, "INTERRUPTED_TRANSACTION_REQUIRES_RECOVERY"):
                module.Cutover(backend, self.checkpoint).return_before_opening()
            self.assertEqual(backend.calls, [])

    def test_restore_failure_holds_current_state_without_reopening(self):
        backend = InventedBackend("verify_private_services")
        def restore_snapshot():
            raise RuntimeError("SYNTHETIC_PRIVATE_DIAGNOSTIC")
        backend.restore_snapshot = restore_snapshot
        with self.assertRaisesRegex(module.Refused, "COHERENT_RETURN_REQUIRES_RECOVERY"):
            module.Cutover(backend, self.checkpoint).execute()
        self.assertNotIn("reopen_previous_services", backend.calls)
        self.assertEqual(self.checkpoint.read(), module.Phase.HELD)

    def test_checkpoint_symlink_and_permissive_directory_refused(self):
        Path(self.folder.name, "phase.json").symlink_to("/never-read")
        with self.assertRaises(OSError):
            self.checkpoint.read()
        os.chmod(self.folder.name, 0o750)
        with self.assertRaises(module.Refused):
            module.Checkpoint(self.folder.name, uid=os.getuid())


if __name__ == "__main__":
    unittest.main()
