import unittest
import transition as T

class Crash(BaseException):pass

class Adapter:
    def __init__(self):
        self.current='old';self.running=True;self.persisted='old';self.journal='prepared'
        self.events=[];self.failure=None;self.committed=False;self.authorized=True
    def event(self,name):
        self.events.append(name)
        if self.failure and self.failure[0]==name:
            error=self.failure[1];self.failure=None;raise error
    def phase(self):return self.journal
    def bind(self):self.event('bind')
    def reserve(self):self.event('reserve')
    def authorize(self):
        self.event('authorize')
        if not self.authorized:raise ValueError('expired')
    def stop(self):self.event('stop');self.running=False
    def stopped(self):self.event('stopped');assert not self.running
    def switch(self,target):
        self.event('switch-'+target);assert not self.running;self.current=target
    def start(self):self.event('start');assert not self.running;self.running=True
    def verify(self,target,*,boot):
        self.event('verify-'+target+('-boot' if boot else ''))
        assert self.running and self.current==target
        if boot:assert self.persisted==target
    def boot(self,target):self.event('boot-'+target);self.persisted=target
    def checkpoint(self,phase):self.event('checkpoint-'+phase);self.journal=phase
    def abort_job(self):self.event('abort');assert self.current==self.persisted=='old'
    def commit_job(self):self.event('commit');self.committed=True
    def verify_complete(self):self.event('complete');assert self.committed;self.verify('new',boot=True)

class Transition(unittest.TestCase):
    def test_success_tests_real_return_and_single_writer_order(self):
        a=Adapter();self.assertEqual(T.promote(a)['code'],'VISE_COMPLETE')
        self.assertEqual([x for x in a.events if x.startswith('switch-')],['switch-new','switch-old','switch-new','switch-new'])
        for i,x in enumerate(a.events):
            if x.startswith('switch-'):self.assertEqual(a.events[i-2:i],['stop','stopped'])
        self.assertTrue(a.committed)
    def test_crash_at_each_operation_resumes(self):
        baseline=Adapter();T.promote(baseline)
        for event in set(baseline.events):
            with self.subTest(event=event):
                a=Adapter();a.failure=(event,Crash())
                with self.assertRaises(Crash):T.promote(a)
                self.assertEqual(T.promote(a)['code'],'VISE_COMPLETE')
    def test_return_intent_precedes_recovery_and_survives_crash(self):
        a=Adapter();a.failure=('verify-new',ValueError())
        original=a.checkpoint
        def checkpoint(p):
            original(p)
            if p=='recovering':raise Crash()
        a.checkpoint=checkpoint
        with self.assertRaises(Crash):T.promote(a)
        self.assertEqual(a.journal,'recovering');a.authorized=False;a.checkpoint=original
        self.assertTrue(T.promote(a)['previous_restored']);self.assertEqual(a.current,'old')
    def test_failed_stop_never_switches_before_proven_exit(self):
        a=Adapter();a.stop=lambda:(_ for _ in ()).throw(TimeoutError())
        self.assertEqual(T.promote(a)['code'],'VISE_RECOVERY_REQUIRED')
        self.assertFalse(any(x.startswith('switch-') for x in a.events));self.assertTrue(a.running)
    def test_ambiguous_commit_response_does_not_rollback(self):
        a=Adapter();original=a.commit_job
        def commit():original();raise OSError()
        a.commit_job=commit
        with self.assertRaises(OSError):T.promote(a)
        self.assertEqual(a.journal,'commit-ready');self.assertEqual(a.current,'new')
        a.commit_job=original;self.assertEqual(T.promote(a)['code'],'VISE_COMPLETE')

if __name__=='__main__':unittest.main()
