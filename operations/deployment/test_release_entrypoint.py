import contextlib
import io
import json
import os
import signal
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import release_entrypoint as entry
from cutover import Checkpoint


class InterfaceTests(unittest.TestCase):
    def run_entry(self, operation='deploy', argv=None, error=None, result=None):
        backend = Mock()
        backend.checkpoint.read.return_value = entry.Phase.HELD
        context = Mock()
        context.__enter__ = Mock(return_value=backend)
        context.__exit__ = Mock(return_value=False)
        engine = Mock()
        engine.execute.return_value = result if result is not None else entry.SUCCESS['deploy']
        engine.execute.side_effect = error
        output = io.StringIO()
        with patch.object(entry, 'OPERATION', operation), patch.object(entry.sys, 'argv', argv or ['sealed']), \
             patch.object(entry.Release, 'immutable_file') as release, patch.object(entry, 'Backend', return_value=context) as factory, \
             patch.object(entry, 'Cutover', return_value=engine) as cutover, \
             patch.object(entry, 'recover_before_opening', return_value=entry.SUCCESS['recover']) as recover, \
             patch.object(entry.resource, 'setrlimit'), patch.object(entry.os, 'umask'), \
             contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            status = entry.main()
        return status, output.getvalue(), backend, factory, cutover, recover, release

    def test_unsealed_and_runtime_arguments_never_reach_backend(self):
        for operation, argv in [(None, ['sealed']), ('deploy', ['sealed', '/etc/private']), ('shell', ['sealed'])]:
            status, output, _, factory, _, _, release = self.run_entry(operation, argv)
            self.assertEqual(status, 1)
            self.assertEqual(json.loads(output)['code'], 'FIRST_RELEASE_REFUSED')
            factory.assert_not_called()
            release.assert_not_called()

    def test_modes_select_only_the_corresponding_engine(self):
        status, output, backend, _, cutover, recover, _ = self.run_entry()
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(output), entry.SUCCESS['deploy'])
        cutover.assert_called_once_with(backend, backend.checkpoint)
        recover.assert_not_called()
        status, output, backend, _, cutover, recover, _ = self.run_entry('recover')
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(output), entry.SUCCESS['recover'])
        cutover.assert_not_called()
        recover.assert_called_once_with(backend, backend.checkpoint)

    def test_private_exception_text_and_subclass_never_escape(self):
        class Untrusted(entry.BackendRefused):
            pass
        for error in (RuntimeError('SYNTHETIC_PRIVATE_VALUE'), entry.BackendRefused('SYNTHETIC_PRIVATE_VALUE'),
                      Untrusted('OPENING_FAILED_CURRENT_STATE_PRESERVED')):
            status, output, *_ = self.run_entry(error=error)
            self.assertEqual(status, 1)
            self.assertNotIn('SYNTHETIC_PRIVATE_VALUE', output)
            self.assertEqual(json.loads(output), {'schema_version': 1, 'code': 'FIRST_RELEASE_REFUSED', 'phase': 'held-for-recovery'})

    def test_only_known_failure_and_validated_phase_are_exported(self):
        status, output, *_ = self.run_entry(error=entry.CutoverRefused('OPENING_FAILED_CURRENT_STATE_PRESERVED'))
        self.assertEqual(status, 1)
        self.assertEqual(json.loads(output), {'schema_version': 1, 'code': 'OPENING_FAILED_CURRENT_STATE_PRESERVED', 'phase': 'held-for-recovery'})

    def test_unexpected_success_payload_cannot_escape(self):
        status, output, *_ = self.run_entry(result={**entry.SUCCESS['deploy'], 'private': 'SYNTHETIC_PRIVATE_VALUE'})
        self.assertEqual(status, 1)
        self.assertNotIn('SYNTHETIC_PRIVATE_VALUE', output)
        self.assertEqual(json.loads(output)['code'], 'FIRST_RELEASE_REFUSED')

    def test_manifest_failure_does_not_enter_backend(self):
        output = io.StringIO()
        with patch.object(entry, 'OPERATION', 'deploy'), patch.object(entry.sys, 'argv', ['sealed']), \
             patch.object(entry.Release, 'immutable_file', side_effect=entry.BackendRefused('RELEASE_HASH_REFUSED')), \
             patch.object(entry, 'Backend') as backend, patch.object(entry.resource, 'setrlimit'), \
             patch.object(entry.os, 'umask'), contextlib.redirect_stdout(output):
            self.assertEqual(entry.main(), 1)
        backend.assert_not_called()
        self.assertEqual(json.loads(output.getvalue()), {'schema_version': 1, 'code': 'RELEASE_HASH_REFUSED', 'phase': 'unavailable'})


class SignalBackend:
    """Invented service operations; the engines/checkpoint/signals are real."""
    def __init__(self, checkpoint, signal_at=None, number=signal.SIGTERM, fail_at=None,
                 repeat_at=None, signal_cleanup=False):
        self.checkpoint = checkpoint
        self.signal_at, self.number, self.fail_at = signal_at, number, fail_at
        self.repeat_at, self.signal_cleanup = repeat_at, signal_cleanup
        self.calls, self.events = [], []
        self.failed = False
        self.holding = False
        self.recovering = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        if self.signal_cleanup:
            self.events.append('cleanup-signal')
            signal.raise_signal(self.number)

    def __getattr__(self, name):
        def operation():
            self.calls.append(name)
            if name == 'hold_current_state':
                self.holding = True
            if name == 'preflight_recovery':
                self.recovering = True
            if name == self.signal_at or name == self.repeat_at:
                self.events.append(name)
                signal.raise_signal(self.number)
            if name == self.fail_at and not self.failed:
                self.failed = True
                raise RuntimeError('INVENTED_PRIVATE_FAILURE_MUST_NOT_ESCAPE')
        return operation


class RealSignalTests(unittest.TestCase):
    def execute(self, *, operation='deploy', signal_at=None, number=signal.SIGTERM,
                fail_at=None, repeat_at=None, signal_cleanup=False):
        before = {number: signal.getsignal(number) for number in (signal.SIGTERM, signal.SIGINT, signal.SIGALRM)}
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Checkpoint(directory, uid=os.getuid())
            if operation == 'recover':
                checkpoint.write(entry.Phase.CANDIDATE, 1)
            backend = SignalBackend(checkpoint, signal_at, number, fail_at, repeat_at, signal_cleanup)
            output = io.StringIO()
            with patch.object(entry, 'OPERATION', operation), patch.object(entry.sys, 'argv', ['sealed']), \
                 patch.object(entry.Release, 'immutable_file'), patch.object(entry, 'Backend', return_value=backend), \
                 patch.object(entry.resource, 'setrlimit'), patch.object(entry.os, 'umask'), \
                 contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                status = entry.main()
            self.assertNotIn('INVENTED_PRIVATE_FAILURE_MUST_NOT_ESCAPE', output.getvalue())
            self.assertEqual({number:signal.getsignal(number) for number in before}, before)
            return status, json.loads(output.getvalue()), backend

    def test_term_before_prepared_never_freezes_or_claims_a_return(self):
        status, result, backend = self.execute(signal_at='preflight')
        self.assertEqual(status, 1)
        self.assertEqual(result, {'schema_version':1, 'code':'RELEASE_INTERRUPTED', 'phase':'unavailable'})
        self.assertEqual(backend.calls, ['preflight'])

    def test_real_term_and_int_before_opening_restore_then_ignore_second_stop(self):
        for number in (signal.SIGTERM, signal.SIGINT):
            with self.subTest(number=number):
                status, result, backend = self.execute(signal_at='verify_private_services', number=number,
                                                        repeat_at='restore_snapshot')
                self.assertEqual(status, 1)
                self.assertEqual(result['code'], 'CUTOVER_REFUSED_PREVIOUS_GENERATION_RESTORED')
                self.assertEqual(result['phase'], entry.Phase.RETURNED.value)
                self.assertIn('restore_snapshot', backend.calls)
                self.assertNotIn('open_public_writes', backend.calls)
                self.assertNotIn('hold_current_state', backend.calls)
                self.assertEqual(backend.events, ['verify_private_services', 'restore_snapshot'])

    def test_real_term_and_int_at_opening_hold_and_never_restore(self):
        for number in (signal.SIGTERM, signal.SIGINT):
            with self.subTest(number=number):
                status, result, backend = self.execute(signal_at='open_public_writes', number=number)
                self.assertEqual(status, 1)
                self.assertEqual(result['code'], 'OPENING_FAILED_CURRENT_STATE_PRESERVED')
                self.assertEqual(result['phase'], entry.Phase.HELD.value)
                self.assertIn('hold_current_state', backend.calls)
                self.assertNotIn('restore_snapshot', backend.calls)
                self.assertNotIn('restore_previous_generation', backend.calls)

    def test_first_stop_during_an_already_engaged_return_is_deferred(self):
        status, result, backend = self.execute(fail_at='verify_private_services', signal_at='restore_snapshot')
        self.assertEqual(status, 1)
        self.assertEqual(result['phase'], entry.Phase.RETURNED.value)
        self.assertIn('reopen_previous_services', backend.calls)
        self.assertNotIn('hold_current_state', backend.calls)

    def test_first_stop_during_containment_does_not_interrupt_held_checkpoint(self):
        status, result, backend = self.execute(fail_at='verify_public_services', signal_at='hold_current_state')
        self.assertEqual(status, 1)
        self.assertEqual(result['phase'], entry.Phase.HELD.value)
        self.assertNotIn('restore_snapshot', backend.calls)

    def test_recovery_finishes_its_existing_return_after_a_soft_stop(self):
        status, result, backend = self.execute(operation='recover', signal_at='preflight_recovery')
        self.assertEqual(status, 0)
        self.assertEqual(result, entry.SUCCESS['recover'])
        self.assertIn('restore_snapshot', backend.calls)
        self.assertIn('reopen_previous_services', backend.calls)

    def test_stop_during_final_cleanup_does_not_turn_verified_success_into_failure(self):
        status, result, backend = self.execute(signal_cleanup=True)
        self.assertEqual(status, 0)
        self.assertEqual(result, entry.SUCCESS['deploy'])
        self.assertEqual(backend.events, ['cleanup-signal'])
        self.assertNotIn('hold_current_state', backend.calls)


if __name__ == '__main__':
    unittest.main()
