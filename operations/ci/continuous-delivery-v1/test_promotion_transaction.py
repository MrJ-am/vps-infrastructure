import unittest
import test_source_observation
import promotion_transaction as P

class PowerLoss(BaseException):pass

class Adapter:
    def __init__(self):
        self.saved='prepared';self.current='old';self.profile='old';self.marker=False;self.deployed=False
        self.events=[];self.cut=None;self.failure=None;self.reject_authority=False;self.fail_return=False
    def event(self,name):
        self.events.append(name)
        if self.cut==len(self.events):raise PowerLoss()
        if self.failure==name:raise RuntimeError('synthetic operation failure')
    def phase(self):return self.saved
    def reserve(self):
        self.marker=not self.deployed;self.event('reserve')
    def authorize(self):
        self.event('authorize')
        if self.reject_authority:raise RuntimeError('invalid authority')
    def ready(self,target):
        if self.fail_return and target=='old':raise RuntimeError('old unavailable')
        self.event('ready-'+target)
    def switch(self,target):self.current=target;self.event('switch-'+target)
    def verify(self,target,*,boot):
        assert self.current==target
        if boot:assert self.profile==target
        self.event('verify-'+target+('-boot' if boot else ''))
    def boot(self,target):self.profile=target;self.event('boot-'+target)
    def checkpoint(self,phase):self.saved=phase;self.event('checkpoint-'+phase)
    def commit_job(self):
        assert self.current==self.profile=='new'
        self.deployed=True;self.marker=False;self.event('commit-job')
    def abort_job(self):
        assert self.current==self.profile=='old'
        self.deployed=False;self.marker=False;self.event('abort-job')
    def verify_complete(self):assert self.deployed and not self.marker and self.current==self.profile=='new'

class Promotion(unittest.TestCase):
    def test_completion_requires_live_and_boot_verified(self):
        a=Adapter();self.assertEqual(P.promote(a)['code'],'PROMOTION_COMPLETE');a.verify_complete()
        self.assertLess(a.events.index('verify-new-boot'),a.events.index('commit-job'))
        self.assertIn('switch-old',a.events)
    def test_process_death_at_every_side_effect_resumes_without_obsolete_or_false_success(self):
        complete=Adapter();P.promote(complete)
        for cut in range(1,len(complete.events)+1):
            with self.subTest(cut=cut):
                a=Adapter();a.cut=cut
                with self.assertRaises(PowerLoss):P.promote(a)
                if a.deployed:self.assertEqual((a.current,a.profile),('new','new'))
                a.cut=None;self.assertEqual(P.promote(a)['code'],'PROMOTION_COMPLETE');a.verify_complete()
    def test_reboot_after_active_checkpoint_reconciles_running_generation(self):
        a=Adapter();a.saved='active';a.marker=True;a.current=a.profile='old'
        self.assertEqual(P.promote(a)['code'],'PROMOTION_COMPLETE');a.verify_complete()
    def test_failure_after_boot_change_restores_both_live_and_boot(self):
        a=Adapter();a.failure='verify-new-boot';r=P.promote(a)
        self.assertTrue(r['previous_restored']);self.assertEqual((a.current,a.profile),('old','old'))
        self.assertFalse(a.deployed);self.assertFalse(a.marker)
    def test_expired_authority_on_resume_returns_old_without_claiming_deployed(self):
        a=Adapter();a.saved='active';a.current='new';a.marker=True;a.reject_authority=True
        r=P.promote(a);self.assertTrue(r['previous_restored']);self.assertFalse(a.deployed)
    def test_failed_return_preserves_reservation_for_recovery(self):
        a=Adapter();a.failure='verify-new';a.fail_return=True
        r=P.promote(a);self.assertFalse(r['previous_restored']);self.assertTrue(a.marker)
        self.assertEqual(a.saved,'recovery-required');self.assertFalse(a.deployed)
    def test_lost_job_commit_result_cannot_rollback_a_committed_delivery(self):
        a=Adapter();a.failure='commit-job'
        with self.assertRaises(RuntimeError):P.promote(a)
        self.assertEqual(a.saved,'commit-ready');self.assertTrue(a.deployed)
        self.assertEqual((a.current,a.profile),('new','new'))
        a.failure=None;self.assertEqual(P.promote(a)['code'],'PROMOTION_COMPLETE');a.verify_complete()
    def test_final_journal_error_does_not_revert_verified_delivery(self):
        a=Adapter();a.failure='checkpoint-complete'
        with self.assertRaises(RuntimeError):P.promote(a)
        self.assertTrue(a.deployed);self.assertEqual((a.current,a.profile),('new','new'))
        a.failure=None;self.assertEqual(P.promote(a)['code'],'PROMOTION_COMPLETE');a.verify_complete()

if __name__=='__main__':unittest.main()
