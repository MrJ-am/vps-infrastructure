"""Fault checks for the control handover; no root operation is executed."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('activation',Path(__file__).with_name('activate-backup-stack.py'))
A=importlib.util.module_from_spec(spec);spec.loader.exec_module(A)

class BackupInterlock(unittest.TestCase):
    def test_backup_in_progress_refuses_before_other_work(self):
        for state in ('active','activating','deactivating','failed'):
            with self.subTest(state=state), patch.object(A,'properties',return_value={'ActiveState':state}), patch.object(A,'run') as command:
                with self.assertRaisesRegex(RuntimeError,'STACK_BACKUP_BUSY'):
                    A.idle()
                command.assert_not_called()

    def test_backup_is_inhibited_with_delivery_writers(self):
        self.assertEqual(A.WRITERS.count('forgejo-backup.service'),1)

class Handover(unittest.TestCase):
    def setUp(self):
        self.effects=[];self.fail=None;self.busy=False;self.active=False
        def command(args,**_):
            self.effects.append(args)
            if args==self.fail:raise RuntimeError('STACK_COMMAND_REFUSED')
            return b''
        def idle():
            if self.busy:raise RuntimeError('STACK_VALIDATION_BUSY')
        self.enterContext(patch.object(A,'run',command))
        self.enterContext(patch.object(A,'idle',idle))
        self.enterContext(patch.object(A,'inhibit',lambda u:self.effects.append(['inhibit',u])))
        self.enterContext(patch.object(A,'release',lambda u:self.effects.append(['release',u])))
        self.enterContext(patch.object(A,'properties',lambda u:{'ActiveState':'active' if self.active else 'inactive'}))
        self.enterContext(patch.object(A.time,'sleep',lambda _:None))
        self.verify=self.enterContext(patch.object(A,'verify',return_value=123))

    def test_busy_validation_has_no_effects(self):
        self.busy=True
        with self.assertRaisesRegex(RuntimeError,'STACK_VALIDATION_BUSY'):A.transition(A.NEW,{}, {})
        self.assertEqual(self.effects,[])

    def test_stop_failure_prevents_configuration_change(self):
        self.fail=[A.CTL,'stop',A.RUNNER]
        with self.assertRaises(RuntimeError):A.transition(A.NEW,{}, {})
        self.assertNotIn([A.NEW+'/bin/switch-to-configuration','test'],self.effects)
        self.assertNotIn(['release',A.RUNNER],self.effects)

    def test_implicit_start_is_refused_with_inhibition_retained(self):
        self.active=True
        with self.assertRaisesRegex(RuntimeError,'STACK_IMPLICIT_RUNNER_START'):A.transition(A.NEW,{}, {})
        self.assertNotIn(['release',A.RUNNER],self.effects)
        self.verify.assert_not_called()

    def test_switch_failure_cannot_start_runner(self):
        self.fail=[A.NEW+'/bin/switch-to-configuration','test']
        with self.assertRaises(RuntimeError):A.transition(A.NEW,{}, {})
        self.assertNotIn([A.CTL,'start',A.RUNNER],self.effects)
        self.verify.assert_not_called()

    def test_start_failure_cannot_claim_verified_handover(self):
        self.fail=[A.CTL,'start',A.RUNNER]
        with self.assertRaises(RuntimeError):A.transition(A.NEW,{}, {})
        self.verify.assert_not_called()

    def test_new_return_new_each_require_runtime_verification(self):
        before={'retained':'fixture'};statuses={'forge':'fixture'}
        for target in (A.NEW,A.OLD,A.NEW):
            self.assertEqual(A.transition(target,before,statuses),123)
            self.verify.assert_called_with(target,before,statuses)
        self.assertEqual(self.verify.call_count,3)
        for target in (A.NEW,A.OLD):
            self.assertIn([target+'/bin/switch-to-configuration','test'],self.effects)

if __name__=='__main__':unittest.main()
