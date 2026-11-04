import unittest
from pathlib import Path
from unittest.mock import Mock,patch
import test_accepted_plan as F
import transition_adapter as A

class Adapter(unittest.TestCase):
    def setUp(self):
        self.f=F.Accepted();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.plan=self.f.compose();self.root=self.f.f.work
        self.state=self.root/'promotion';self.state.mkdir(mode=0o700)
        self.jobs=self.root/'jobs';self.jobs.mkdir(mode=0o700)
        self.acceptance=self.root/'acceptance';self.acceptance.mkdir(mode=0o700)
        for p in (self.jobs/self.plan['job'],self.acceptance/'vise-plans',self.acceptance/self.plan['job']):p.mkdir(mode=0o700)
        self.job={**self.f.job,'schema_version':1}
        A.O.save(self.jobs/self.plan['job']/'state.json',self.job)
        A.O.save(self.acceptance/'commit.json',self.f.owner)
        A.O.save(self.acceptance/'vise-plans'/(self.plan['job']+'.json'),self.f.plan)
        A.O.save(self.acceptance/self.plan['job']/'state.json',self.f.ledger)
        A.O.save(self.state/'plan.json',self.plan)
        for name,value in [('JOBS',self.jobs),('ACCEPTANCE',self.acceptance)]:
            p=patch.object(A,name,value);p.start();self.addCleanup(p.stop)
        self.adapter=A.Adapter(self.state,'synthetic-reader')
    def test_journal_binds_plan_and_rejects_other_digest(self):
        self.assertEqual(self.adapter.phase(),'prepared');self.adapter.checkpoint('recovering')
        self.assertEqual(self.adapter.phase(),'recovering')
        A.O.save(self.adapter.journal,{'schema_version':1,'plan_sha256':'f'*64,'phase':'recovering'})
        with self.assertRaisesRegex(Exception,'VISE_TRANSITION_JOURNAL_REFUSED'):self.adapter.phase()
    def test_bind_rechecks_saved_acceptance_and_layout(self):
        with patch.object(A.L,'verify') as layout,patch.object(A.L,'read',return_value=(
                'ExecStart='+self.plan['previous_artifact']+'/server\n').encode()),\
                patch.object(self.adapter,'retained',return_value={'nginx':b'unchanged'}):
            self.adapter.bind();layout.assert_called_once()
            self.assertEqual(self.adapter.before,{'nginx':b'unchanged'})
    def test_changed_acceptance_prevents_layout_or_operations(self):
        A.O.save(self.acceptance/self.plan['job']/'state.json',{})
        with patch.object(A.L,'verify') as layout:
            with self.assertRaisesRegex(Exception,'VISE_TRANSITION_ACCEPTANCE_CHANGED'):self.adapter.bind()
            layout.assert_not_called()
    def test_reserve_requires_known_current_and_boot(self):
        with patch.object(A.R,'actual',return_value=(self.plan['old'],self.plan['old'])):
            self.adapter.reserve()
        self.assertEqual(A.O.read(self.adapter.job)['promotion'],self.adapter.marker)
        with patch.object(A.R,'actual',return_value=('/other',self.plan['old'])):
            with self.assertRaisesRegex(Exception,'VISE_TRANSITION_LIVE_BASE_CHANGED'):self.adapter.reserve()
    def test_forward_requires_graceful_exit_and_empty_cgroup(self):
        with patch.object(A.P,'stopped') as stopped,patch.object(A,'run',return_value=b'Result=success\nExecMainCode=1\nExecMainStatus=0\n'):
            self.adapter.stopped();stopped.assert_called_once()
        with patch.object(A.P,'stopped'),patch.object(A,'run',return_value=b'Result=signal\nExecMainCode=2\nExecMainStatus=9\n'):
            with self.assertRaisesRegex(Exception,'VISE_TRANSITION_STOP_NOT_GRACEFUL'):self.adapter.stopped()
    def test_recovery_can_restore_after_candidate_crash_but_requires_empty_cgroup(self):
        self.adapter.checkpoint('recovering')
        with patch.object(A.P,'stopped') as stopped,patch.object(A,'run') as run:
            self.adapter.stopped();stopped.assert_called_once();run.assert_not_called()
        with patch.object(A.P,'stopped',side_effect=ValueError('writer remains')):
            with self.assertRaisesRegex(ValueError,'writer remains'):self.adapter.stopped()
    def test_switch_requires_stop_before_and_after_fixed_generation_command(self):
        with patch.object(self.adapter,'stopped') as stopped,patch.object(A.P,'stopped') as after,\
                patch.object(A.os.path,'realpath',return_value=self.plan['old']),patch.object(A,'run') as run:
            self.adapter.switch('new');self.assertEqual(stopped.call_count,2)
            run.assert_called_once_with([self.plan['new']+'/bin/switch-to-configuration','test'])
    def test_live_writer_prevents_switch(self):
        with patch.object(self.adapter,'stopped',side_effect=ValueError('writer remains')),patch.object(A,'run') as run:
            with self.assertRaisesRegex(ValueError,'writer remains'):self.adapter.switch('new')
            run.assert_not_called()
    def test_unknown_target_never_executes(self):
        with patch.object(A,'run') as run:
            with self.assertRaisesRegex(Exception,'VISE_TRANSITION_TARGET_REFUSED'):self.adapter.boot('candidate-command')
            run.assert_not_called()
    def test_completed_history_does_not_require_current_acceptance_owner(self):
        self.adapter.checkpoint('complete');(self.acceptance/'commit.json').unlink()
        with patch.object(A.L,'verify') as layout:self.adapter.bind();layout.assert_not_called()
    def test_unfinished_backup_prevents_reservation(self):
        value={'schema_version':1,'phase':'offline','restart_required':True,'capture_id':'a'*32}
        with patch.object(Path,'exists',return_value=True),patch.object(A.S,'read',return_value=value),\
                patch.object(A.R,'reserve') as reserve:
            with self.assertRaisesRegex(Exception,'VISE_TRANSITION_BACKUP_RECOVERY_PENDING'):self.adapter.reserve()
            reserve.assert_not_called()
    def test_completed_backup_allows_transition_preflight(self):
        value={'schema_version':1,'phase':'complete','restart_required':True,'capture_id':'a'*32}
        with patch.object(Path,'exists',return_value=True),patch.object(A.S,'read',return_value=value):
            self.adapter.backup_idle()
    def test_inhibitor_is_owned_durable_and_removed_before_explicit_start(self):
        hold=self.root/'hold/hold.json';dropin=self.root/'dropin/inhibit.conf'
        with patch.object(A,'HOLD',hold),patch.object(A,'DROPIN',dropin),patch.object(A,'run') as run:
            self.adapter.stop()
            self.assertEqual(A.S.read(hold)['plan_sha256'],self.adapter.key)
            self.assertEqual(dropin.read_bytes(),A.INHIBITOR)
            self.assertEqual(run.call_args_list[-1].args[0],[A.P.CTL,'stop','vise.service'])
            self.adapter.inhibitor(True)  # Re-entry after interruption keeps same owner.
            self.adapter.start();self.assertFalse(hold.exists());self.assertFalse(dropin.exists())
            self.assertEqual(run.call_args_list[-1].args[0],[A.P.CTL,'start','vise.service'])
    def test_other_transition_cannot_steal_inhibitor(self):
        hold=self.root/'hold/hold.json';dropin=self.root/'dropin/inhibit.conf'
        with patch.object(A,'HOLD',hold),patch.object(A,'DROPIN',dropin),patch.object(A,'run') as run:
            self.adapter.inhibitor(True);run.reset_mock()
            A.O.save(hold,{'schema_version':1,'plan_sha256':'f'*64})
            with self.assertRaisesRegex(Exception,'VISE_TRANSITION_HOLD_CHANGED'):self.adapter.start()
            run.assert_not_called();self.assertTrue(dropin.exists())

if __name__=='__main__':unittest.main()
