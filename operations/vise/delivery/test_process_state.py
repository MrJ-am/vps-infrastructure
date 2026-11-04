import unittest
from unittest.mock import patch
import process_state as P

class Process(unittest.TestCase):
    def test_wait_requires_eventual_exact_identity(self):
        identity={'pid':42}
        with patch.object(P,'running_identity',side_effect=[ValueError('VISE_PROCESS_IDENTITY_CHANGED'),identity]) as check,\
                patch.object(P.time,'sleep'):
            self.assertEqual(P.wait_running_identity('/synthetic'),identity)
            self.assertEqual(check.call_count,2)
    def test_persistent_wrong_identity_times_out(self):
        with patch.object(P,'running_identity',side_effect=ValueError('VISE_PROCESS_IDENTITY_CHANGED')),\
                patch.object(P.time,'monotonic',side_effect=[0,11]),patch.object(P.time,'sleep'):
            with self.assertRaisesRegex(ValueError,'VISE_PROCESS_START_TIMEOUT'):P.wait_running_identity('/synthetic')
    def test_wait_does_not_swallow_malformed_observations(self):
        with patch.object(P,'running_identity',side_effect=ValueError('VISE_PROCESS_STATUS_REFUSED')):
            with self.assertRaisesRegex(ValueError,'VISE_PROCESS_STATUS_REFUSED'):P.wait_running_identity('/synthetic')
    def setUp(self):
        self.raw=b'ActiveState=inactive\nSubState=dead\nMainPID=0\nControlPID=0\nControlGroup=\nJob=\nExecMainStartTimestampMonotonic=123\n'
        self.stopped=P.parse(self.raw)
    def test_idle_empty_cgroup_accepted(self):P.stopped_evidence(self.stopped,False,dict(self.stopped))
    def test_failed_unit_allowed_only_for_recovery_with_no_writer(self):
        failed={**self.stopped,'ActiveState':'failed','SubState':'failed'}
        with self.assertRaises(ValueError):P.stopped_evidence(failed,False,failed)
        P.stopped_evidence(failed,False,failed,allow_failed=True)
        with self.assertRaises(ValueError):P.stopped_evidence(failed,True,failed,allow_failed=True)
    def test_remaining_descendant_refused(self):
        with self.assertRaisesRegex(ValueError,'VISE_PROCESS_NOT_STOPPED'):P.stopped_evidence(self.stopped,True,self.stopped)
    def test_each_pending_process_or_job_refused(self):
        for key,value in [('ActiveState','deactivating'),('SubState','stop-sigterm'),('MainPID',42),('ControlPID',43),('Job','1')]:
            state={**self.stopped,key:value}
            with self.subTest(key=key),self.assertRaises(ValueError):P.stopped_evidence(state,False,state)
    def test_race_between_observations_refused(self):
        with self.assertRaises(ValueError):P.stopped_evidence(self.stopped,False,{**self.stopped,'MainPID':123})
    def test_malformed_or_foreign_status_refused(self):
        for raw in [self.raw+b'MainPID=0\n',self.raw.replace(b'ControlGroup=\n',b'ControlGroup=/other\n'),
            self.raw.replace(b'MainPID=0',b'MainPID=-1'),self.raw.replace(b'Job=\n',b'')]:
            with self.assertRaises(ValueError):P.parse(raw)

if __name__=='__main__':unittest.main()
