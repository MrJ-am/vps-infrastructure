import unittest
import test_source_observation
import staging_transaction as S

class PowerLoss(BaseException):pass

class Adapter:
    def __init__(self):
        self.saved='prepared';self.current=self.profile='old';self.running=True
        self.lease=True;self.events=[];self.cut=None;self.failure=None
        self.expired=False;self.clients=False;self.broken_return=False
        self.public=('blue',123);self.reference=self.public
    def event(self,name):
        self.events.append(name)
        if len(self.events)==self.cut:raise PowerLoss()
        if self.failure==name:raise RuntimeError('injected failure')
    def phase(self):return self.saved
    def bind(self):self.event('bind')
    def authorize(self):
        self.event('authorize')
        if self.expired:raise RuntimeError('expired')
    def no_clients(self):
        self.event('no-clients')
        if self.clients:raise RuntimeError('clients remain')
    def stop_slot(self):self.running=False;self.event('stop')
    def switch(self,target):
        if self.broken_return and target=='old':raise RuntimeError('return failed')
        self.current=target;self.event('switch-'+target)
    def start_slot(self):self.running=True;self.event('start')
    def verify(self,target,*,boot):
        assert self.current==target and self.running and self.public==self.reference
        if boot:assert self.profile==target
        self.event('verify-'+target+('-boot' if boot else ''))
    def boot(self,target):self.profile=target;self.event('boot-'+target)
    def checkpoint(self,phase):self.saved=phase;self.event('checkpoint-'+phase)
    def release(self):
        assert self.current==self.profile=='old' and self.running
        self.lease=False;self.event('release')

class Staging(unittest.TestCase):
    def test_ready_requires_real_return_and_persistent_staged_generation(self):
        a=Adapter();r=S.stage(a)
        self.assertEqual(r['code'],'STAGING_READY');self.assertFalse(r['deployed'])
        self.assertEqual((a.current,a.profile,a.saved),('new','new','ready'))
        self.assertTrue(a.lease)
        self.assertLess(a.events.index('verify-old'),a.events.index('boot-new'))
    def test_power_loss_at_every_boundary_can_resume_after_reboot(self):
        complete=Adapter();S.stage(complete)
        for cut in range(1,len(complete.events)+1):
            with self.subTest(cut=cut):
                a=Adapter();a.cut=cut
                with self.assertRaises(PowerLoss):S.stage(a)
                a.cut=None;a.current=a.profile;a.running=True
                self.assertEqual(S.stage(a)['code'],'STAGING_READY')
                self.assertEqual((a.current,a.profile),('new','new'))
                self.assertEqual(a.public,a.reference)
    def test_readiness_failure_restores_current_and_boot(self):
        a=Adapter();a.failure='verify-new-boot';r=S.stage(a)
        self.assertEqual(r['code'],'STAGING_FAILED');self.assertTrue(r['previous_restored'])
        self.assertEqual((a.current,a.profile,a.saved),('old','old','failed'))
        self.assertFalse(a.lease)
    def test_expiry_while_resuming_restores_old_generation(self):
        a=Adapter();a.saved='active';a.current='new';a.expired=True
        self.assertEqual(S.stage(a)['code'],'STAGING_FAILED')
        self.assertEqual((a.current,a.profile),('old','old'))
    def test_clients_prevent_stopping_slot_and_keep_recovery_lease(self):
        a=Adapter();a.clients=True
        self.assertEqual(S.stage(a)['code'],'STAGING_RECOVERY_REQUIRED')
        self.assertNotIn('stop',a.events);self.assertTrue(a.lease)
        a.clients=False
        self.assertEqual(S.stage(a)['code'],'STAGING_FAILED');self.assertFalse(a.lease)
    def test_failed_return_is_retried_without_authorizing_candidate(self):
        a=Adapter();a.failure='verify-new';a.broken_return=True
        self.assertEqual(S.stage(a)['code'],'STAGING_RECOVERY_REQUIRED')
        self.assertTrue(a.lease)
        a.failure=None;a.broken_return=False;a.expired=True;a.events=[]
        self.assertEqual(S.stage(a)['code'],'STAGING_FAILED')
        self.assertNotIn('authorize',a.events);self.assertFalse(a.lease)
    def test_crash_during_every_recovery_step_resumes_recovery(self):
        complete=Adapter();complete.failure='verify-new';S.stage(complete)
        start=complete.events.index('checkpoint-recovery-required')+1
        for cut in range(start,len(complete.events)+1):
            with self.subTest(cut=cut):
                a=Adapter();a.failure='verify-new';a.cut=cut
                with self.assertRaises(PowerLoss):S.stage(a)
                a.cut=None;a.failure=None;a.current=a.profile;a.running=True;a.events=[]
                self.assertEqual(S.stage(a)['code'],'STAGING_FAILED')
                self.assertNotIn('authorize',a.events);self.assertFalse(a.lease)
    def test_lost_ready_ack_never_rolls_back_published_ready_stage(self):
        a=Adapter();a.failure='checkpoint-ready'
        with self.assertRaises(RuntimeError):S.stage(a)
        self.assertEqual((a.current,a.profile,a.saved),('new','new','ready'))
        self.assertTrue(a.lease);a.failure=None
        self.assertEqual(S.stage(a)['code'],'STAGING_READY')
    def test_ready_recheck_failure_cannot_undo_an_ambiguous_merge(self):
        a=Adapter();S.stage(a);a.failure='verify-new-boot';a.events=[]
        with self.assertRaises(RuntimeError):S.stage(a)
        self.assertEqual(a.events,['bind','verify-new-boot'])
        self.assertEqual((a.current,a.profile,a.saved),('new','new','ready'))
        self.assertTrue(a.lease)

if __name__=='__main__':unittest.main()
