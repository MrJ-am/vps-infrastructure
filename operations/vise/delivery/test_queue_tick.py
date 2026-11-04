import copy,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
import test_accepted_plan as F
import queue_tick as Q

class Queue(unittest.TestCase):
    def setUp(self):
        self.f=F.Accepted();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.paths={k:self.root/k for k in ('state','jobs','acceptance','staging','roots')}
        for path in self.paths.values():path.mkdir(mode=0o700)
        self.job=copy.deepcopy(self.f.job);self.job['schema_version']=1;self.plan=self.f.compose()
        self.owner=Q.K.identity(self.job)
        self.jobpath=self.paths['jobs']/self.job['id'];self.jobpath.mkdir(mode=0o700)
        self.ledgerpath=self.paths['acceptance']/self.job['id'];self.ledgerpath.mkdir(mode=0o700)
        Q.O.save(self.jobpath/'state.json',self.job)
        Q.O.save(self.paths['acceptance']/'commit.json',self.owner)
        Q.O.save(self.ledgerpath/'state.json',self.f.ledger)
        self.credential=Mock(return_value='synthetic-observer')
        self.publish=Mock(return_value={'code':'PROMOTION_PLAN_ENQUEUED'})
        p=patch.object(Q.E,'publish',self.publish);p.start();self.addCleanup(p.stop)
    def tick(self):return Q.tick(credential=self.credential,**self.paths)
    def previous(self,phase):
        key=Q.N.R.identity(self.plan)['plan_sha256']
        Q.O.save(self.paths['state']/'plan.json',self.plan)
        Q.O.save(self.paths['state']/(key+'.json'),{'schema_version':1,'plan_sha256':key,'phase':phase})
        return key
    def test_fully_accepted_owner_invokes_verified_publisher(self):
        self.assertEqual(self.tick()['code'],'PROMOTION_PLAN_ENQUEUED')
        self.publish.assert_called_once_with(self.paths['state'],self.paths['roots'],self.paths['jobs'],
            self.paths['acceptance'],self.job['id'],'synthetic-observer')
    def test_active_or_recovering_plan_always_resumes_without_enqueue(self):
        for phase in ('prepared','new-tested','returned','active','boot','commit-ready','recovering'):
            self.previous(phase);self.assertIsNone(self.tick())
        self.publish.assert_not_called();self.credential.assert_not_called()
    def test_platform_lease_blocks_vise_even_when_symlink_is_dangling(self):
        (self.paths['staging']/'lease.json').symlink_to(self.root/'missing')
        self.assertEqual(self.tick()['code'],'VISE_QUEUE_PLATFORM_PENDING')
        self.publish.assert_not_called();self.credential.assert_not_called()
    def test_platform_acceptance_owner_is_left_to_platform_worker(self):
        self.job['capture']['proposal'].update(repository='mrjam-plateforme',repository_id=1437120781)
        Q.O.save(self.jobpath/'state.json',self.job)
        self.assertEqual(self.tick()['code'],'VISE_QUEUE_PLATFORM_PENDING');self.publish.assert_not_called()
    def test_incomplete_sync_does_not_load_credential_or_enqueue(self):
        ledger=copy.deepcopy(self.f.ledger);ledger['receipts'].pop('sync')
        Q.O.save(self.ledgerpath/'state.json',ledger)
        self.assertEqual(self.tick()['code'],'VISE_QUEUE_ACCEPTANCE_PENDING')
        self.publish.assert_not_called();self.credential.assert_not_called()
    def test_returned_vise_attempt_is_not_automatically_retried(self):
        key=self.previous('failed')
        self.job['delivery_return']={'plan_sha256':key,'generation':self.plan['old']}
        Q.O.save(self.jobpath/'state.json',self.job)
        for _ in range(2):self.assertEqual(self.tick()['code'],'VISE_QUEUE_RETURNED')
        self.publish.assert_not_called();self.credential.assert_not_called()
    def test_unproven_failure_cannot_be_ignored(self):
        self.previous('failed')
        with self.assertRaisesRegex(Exception,'ENQUEUE_FAILED_RETURN_UNPROVEN'):self.tick()
        self.publish.assert_not_called()
    def test_owner_path_escape_is_refused_before_reading_job(self):
        Q.O.save(self.paths['acceptance']/'commit.json',{**self.owner,'job':'../unexpected'})
        with self.assertRaisesRegex(Exception,'VISE_QUEUE_OWNER_REFUSED'):self.tick()
        self.publish.assert_not_called()

if __name__=='__main__':unittest.main()
