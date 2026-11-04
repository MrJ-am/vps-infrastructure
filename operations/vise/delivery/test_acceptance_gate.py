import tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
import test_preparation_plan
import acceptance_gate as G

class Gate(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);root=Path(self.tmp.name)
        self.state=root/'acceptance';self.jobs=root/'jobs';self.prepared=root/'prepared';self.staging=root/'staging'
        for p in (self.state,self.jobs,self.prepared,self.staging):p.mkdir(mode=0o700)
        self.job={'schema_version':1,'id':'a'*64,'phase':'validated','capture':{'proposal_sha256':'b'*64},'ready':{'base_sha256':'c'*64}}
        self.environment={'system':'synthetic'};key=G.O.sha(G.O.encode(self.environment))
        self.work=self.prepared/self.job['id']/key;self.work.parent.mkdir(mode=0o700);self.work.mkdir(mode=0o700)
        directory=self.jobs/self.job['id'];directory.mkdir(mode=0o700);G.O.save(directory/'state.json',self.job)
        self.plan={**G.K.identity(self.job),'profile':'vise-v1','deployment_authorized':False}
        p=patch.object(G.P,'create',return_value=self.plan);self.create=p.start();self.addCleanup(p.stop)
        self.observe=Mock(return_value=self.environment);self.verify=object()
    def ready(self):
        return G.ready(self.state,self.jobs,self.prepared,self.staging,self.job,self.verify,
            recipe=Path('/fixed/generations.nix'),observe=self.observe)
    def saved(self):return G.L.read(self.state/'vise-plans'/(self.job['id']+'.json'))
    def test_plan_persisted_before_commit_and_rechecked_on_retry(self):
        self.assertEqual(self.ready(),self.plan);self.assertEqual(self.saved(),self.plan)
        self.assertFalse((self.state/'commit.json').exists())
        G.K.acquire(self.state,self.jobs,self.job)
        self.assertEqual(self.ready(),self.plan);self.assertEqual(self.create.call_count,2)
    def test_platform_staging_blocks_vise_acceptance(self):
        G.O.save(self.staging/'lease.json',{})
        with self.assertRaisesRegex(Exception,'VISE_OTHER_STAGE_PENDING'):self.ready()
        self.create.assert_not_called()
    def test_dangling_staging_link_also_blocks(self):
        (self.staging/'lease.json').symlink_to(self.staging/'absent')
        with self.assertRaisesRegex(Exception,'VISE_OTHER_STAGE_PENDING'):self.ready()
    def test_other_pending_acceptance_blocks_before_verification(self):
        other={**self.job,'id':'d'*64};directory=self.jobs/other['id'];directory.mkdir(mode=0o700)
        G.O.save(directory/'state.json',other);G.K.acquire(self.state,self.jobs,other)
        with self.assertRaisesRegex(Exception,'VISE_OTHER_ACCEPTANCE_PENDING'):self.ready()
        self.create.assert_not_called()
    def test_accepted_plan_is_immutable(self):
        self.ready();G.K.acquire(self.state,self.jobs,self.job)
        self.create.return_value={**self.plan,'changed':True}
        with self.assertRaisesRegex(Exception,'VISE_ACCEPTED_PLAN_CHANGED'):self.ready()
        self.assertEqual(self.saved(),self.plan)
    def test_committed_job_without_plan_cannot_recover_by_invention(self):
        G.K.acquire(self.state,self.jobs,self.job)
        with self.assertRaisesRegex(Exception,'VISE_ACCEPTED_PLAN_CHANGED'):self.ready()
    def test_premerge_failure_does_not_reserve_acceptance(self):
        self.create.side_effect=ValueError('authority refused')
        with self.assertRaisesRegex(ValueError,'authority refused'):self.ready()
        self.assertFalse((self.state/'commit.json').exists());self.assertFalse((self.state/'vise-plans').exists())
    def test_changed_live_environment_prevents_plan_publication(self):
        self.observe.side_effect=[self.environment,{'system':'other'}]
        with self.assertRaisesRegex(Exception,'VISE_ACCEPTANCE_ENVIRONMENT_CHANGED'):self.ready()
        self.assertFalse((self.state/'vise-plans').exists())
    def test_premerge_plan_can_be_reprepared(self):
        self.ready();self.create.return_value={**self.plan,'new_preparation':True}
        self.assertEqual(self.ready(),self.create.return_value);self.assertEqual(self.saved(),self.create.return_value)

if __name__=='__main__':unittest.main()
