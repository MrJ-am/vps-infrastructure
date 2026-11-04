import unittest
from unittest.mock import Mock
import test_staging_lease as F
import staging_queue as Q

class Queue(unittest.TestCase):
    def setUp(self):
        self.fixture=F.Lease();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        f=self.fixture;self.prepared=f.state/'prepared';self.prepared.mkdir(mode=0o700)
        self.adapter=Mock();self.adapter.environment.return_value=f.plan['old'];self.adapter.supports.return_value=True
        self.adapter.prepare.return_value=f.plan
        self.adapter.stage.return_value={'code':'STAGING_READY'}
        self.adapter.acquire.side_effect=lambda plan:f.acquire(plan)
        self.work=self.prepared/f.job['id']/Q.O.sha(Q.O.encode(f.plan['old']))
        self.work.parent.mkdir(mode=0o700);self.work.mkdir(mode=0o700);Q.O.save(self.work/'ready.json',{})
    def tick(self):
        f=self.fixture;return Q.tick(f.state,f.jobs,self.prepared,self.adapter,clock=lambda:1000)
    def save(self):
        f=self.fixture;Q.O.save(f.jobs/f.job['id']/'state.json',f.job)
    def test_selection_reserves_without_activating_then_resumes_same_plan(self):
        self.assertEqual(self.tick()['code'],'STAGING_RESERVED');self.adapter.stage.assert_not_called()
        self.assertEqual(self.tick()['code'],'STAGING_READY');self.adapter.stage.assert_called_once_with(self.fixture.plan)
        self.adapter.prepare.assert_called_once()
    def test_promotion_in_progress_is_never_interrupted_by_stager(self):
        self.fixture.acquire();self.fixture.job['promotion']={'schema_version':1,'plan_sha256':'f'*64,'proposal_sha256':'c'*64};self.save()
        self.assertEqual(self.tick()['code'],'STAGING_PROMOTION_PENDING')
        self.adapter.stage.assert_not_called();self.adapter.complete.assert_not_called()
    def test_deployed_job_requires_completion_verifier_instead_of_reactivation(self):
        self.fixture.acquire();self.fixture.job['phase']='deployed';self.save()
        self.assertEqual(self.tick()['code'],'STAGING_DELIVERY_COMPLETE')
        self.adapter.complete.assert_called_once_with(self.fixture.plan,self.fixture.job);self.adapter.stage.assert_not_called()
    def test_active_ci_prevents_new_stage(self):
        self.fixture.job['phase']='running';self.save()
        self.assertEqual(self.tick()['code'],'STAGING_CI_BUSY');self.adapter.environment.assert_not_called()
    def test_unsupported_project_does_not_acquire_reservation(self):
        self.adapter.supports.return_value=False
        self.assertEqual(self.tick()['code'],'STAGING_IDLE');self.adapter.acquire.assert_not_called()
    def test_failed_returned_job_is_backed_off(self):
        f=self.fixture;f.acquire()
        def stage(plan):
            Q.L.checkpoint(f.state,plan,'failed');f.release();return {'code':'STAGING_FAILED','previous_restored':True}
        self.adapter.stage.side_effect=stage
        self.assertEqual(self.tick()['code'],'STAGING_FAILED')
        self.assertEqual(self.tick()['code'],'STAGING_IDLE');self.adapter.prepare.assert_not_called()
    def test_incomplete_preparation_is_not_staged(self):
        (self.work/'ready.json').unlink()
        self.assertEqual(self.tick()['code'],'STAGING_IDLE');self.adapter.prepare.assert_not_called()
    def test_expired_preparation_does_not_reserve_and_is_backed_off(self):
        self.adapter.prepare.side_effect=RuntimeError('synthetic private detail')
        self.assertEqual(self.tick()['code'],'STAGING_PREPARATION_RETRY')
        self.adapter.acquire.assert_not_called()
        self.assertEqual(self.tick()['code'],'STAGING_IDLE')
        self.adapter.prepare.assert_called_once()

if __name__=='__main__':unittest.main()
