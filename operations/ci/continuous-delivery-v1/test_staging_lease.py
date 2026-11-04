import copy,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'authority-v1'))
import test_admission_orchestrator
import test_generation_views as V
import staging_lease as L

class PowerLoss(BaseException):pass

class Lease(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name)
        self.state=root/'staging';self.acceptance=root/'acceptance';self.jobs=root/'jobs'
        for p in (self.state,self.acceptance,self.jobs):p.mkdir(mode=0o700)
        v=V.Views();v.setUp()
        self.plan={'schema_version':1,'job':'d'*64,'proposal_sha256':'c'*64,'base_sha256':'e'*64,'slot':'green',
            'old':v.state,'staged':v.views['stage']['state'],'promoted':v.views['promotion']['state'],
            'candidate':v.p('candidate'),'bundle':v.p('bundle'),'preparation_sha256':'f'*64}
        self.actual=(v.state['system'],v.state['system'])
        self.job={'schema_version':1,'id':'d'*64,'phase':'validated','capture':{'proposal_sha256':'c'*64},'ready':{'base_sha256':'e'*64}}
        (self.jobs/self.job['id']).mkdir(mode=0o700);L.O.save(self.jobs/self.job['id']/'state.json',self.job)
    def acquire(self,plan=None):return L.acquire(self.state,plan or self.plan,self.acceptance,self.jobs,lambda:self.actual)
    def release(self):L.release(self.state,self.plan,self.acceptance,self.jobs,lambda:self.actual)
    def committed(self):L.O.save(self.acceptance/'commit.json',L.K.identity(self.job))
    def test_same_owner_resumes_and_second_owner_is_refused(self):
        identity=self.acquire();self.assertEqual(self.acquire(),identity)
        second=copy.deepcopy(self.plan);second['job']='a'*64
        with self.assertRaisesRegex(Exception,'STAGING_OTHER_DELIVERY_PENDING'):self.acquire(second)
    def test_plan_journal_precede_lease_even_when_process_dies(self):
        save=L.O.save
        for cut in range(1,4):
            with self.subTest(cut=cut),tempfile.TemporaryDirectory() as temporary:
                state=Path(temporary);calls=[]
                def interrupted(path,value):
                    save(path,value);calls.append(path.name)
                    if len(calls)==cut:raise PowerLoss()
                with patch.object(L.O,'save',side_effect=interrupted):
                    with self.assertRaises(PowerLoss):L.acquire(state,self.plan,self.acceptance,self.jobs,lambda:self.actual)
                self.assertEqual(L.acquire(state,self.plan,self.acceptance,self.jobs,lambda:self.actual),L.identity(self.plan))
                if cut==3:self.assertEqual(calls[-1],'lease.json')
    def test_ambiguous_acceptance_prevents_new_stage(self):
        self.committed()
        with self.assertRaisesRegex(Exception,'STAGING_ACCEPTED_DELIVERY_PENDING'):self.acquire()
        self.assertFalse((self.state/'lease.json').exists())
    def test_failed_stage_releases_only_after_real_live_and_boot_return(self):
        self.acquire();L.checkpoint(self.state,self.plan,'failed')
        self.actual=(self.plan['staged']['system'],self.plan['old']['system'])
        with self.assertRaisesRegex(Exception,'STAGING_RETURN_NOT_PROVEN'):self.release()
        self.assertTrue((self.state/'lease.json').exists())
        self.actual=(self.plan['old']['system'],)*2;self.release();self.release()
        self.assertFalse((self.state/'lease.json').exists())
    def test_accepted_job_cannot_release_its_reservation(self):
        self.acquire();self.committed();L.checkpoint(self.state,self.plan,'failed')
        with self.assertRaisesRegex(Exception,'STAGING_AMBIGUOUS_ACCEPTANCE_RETAINED'):self.release()
        self.assertTrue((self.state/'lease.json').exists())
    def test_ready_record_cannot_be_reused_if_lease_was_removed(self):
        self.acquire();L.checkpoint(self.state,self.plan,'ready',{'synthetic':'runtime'})
        (self.state/'lease.json').unlink()
        with self.assertRaisesRegex(Exception,'STAGING_RELEASED_RECORD_REFUSED'):self.acquire()
    def test_failed_unaccepted_plan_can_be_retried_after_fresh_preparation(self):
        self.acquire();L.checkpoint(self.state,self.plan,'failed');self.release();self.acquire()
        key=L.identity(self.plan)['plan_sha256']
        self.assertEqual(L.read(self.state/'records'/(key+'.json'))['phase'],'prepared')
    def test_missing_completion_receipt_does_not_clear_acceptance(self):
        self.committed();self.job['phase']='deployed';L.O.save(self.jobs/self.job['id']/'state.json',self.job)
        with self.assertRaisesRegex(Exception,'STAGING_ACCEPTED_DELIVERY_PENDING'):self.acquire()
    def promoted(self):
        self.acquire();L.checkpoint(self.state,self.plan,'ready',{'synthetic':'runtime'})
        self.promotion=self.state/'promotion';self.promotion.mkdir(mode=0o700)
        p={'schema_version':1,'job':self.plan['job'],'proposal_sha256':self.plan['proposal_sha256'],
            'old':self.plan['staged']['system'],'new':self.plan['promoted']['system'],'slot':'green',
            'bundle':self.plan['bundle'],'forge_pull':1,'review':{}}
        self.key=L.C.sha(L.O.encode(p));L.O.save(self.promotion/'plan.json',p)
        L.O.save(self.promotion/(self.key+'.json'),{'schema_version':1,'plan_sha256':self.key,'phase':'complete'})
        self.job.update(phase='deployed',delivery={'plan_sha256':self.key,'proposal_sha256':self.plan['proposal_sha256'],
            'generation':p['new'],'previous_generation':p['old']})
        self.actual=(p['new'],)*2
    def finish(self):L.complete(self.state,self.plan,self.job,self.promotion,lambda:self.actual)
    def test_verified_promotion_retires_lease_idempotently(self):
        self.promoted();self.finish();self.finish()
        self.assertFalse((self.state/'lease.json').exists())
        key=L.identity(self.plan)['plan_sha256'];self.assertEqual(L.read(self.state/'records'/(key+'.json'))['phase'],'complete')
    def test_job_deployed_without_terminal_promotion_does_not_release(self):
        self.promoted();L.O.save(self.promotion/(self.key+'.json'),{'schema_version':1,'plan_sha256':self.key,'phase':'commit-ready'})
        with self.assertRaisesRegex(Exception,'STAGING_PROMOTION_NOT_COMPLETE'):self.finish()
        self.assertTrue((self.state/'lease.json').exists())
    def test_different_live_generation_does_not_release(self):
        self.promoted();self.actual=(self.plan['staged']['system'],)*2
        with self.assertRaisesRegex(Exception,'STAGING_PROMOTED_GENERATION_CHANGED'):self.finish()
        self.assertTrue((self.state/'lease.json').exists())
    def test_other_delivery_receipt_does_not_release(self):
        self.promoted();self.job['delivery']['plan_sha256']='0'*64
        with self.assertRaisesRegex(Exception,'STAGING_DELIVERY_RECEIPT_CHANGED'):self.finish()
    def test_crash_after_completion_record_before_unlink_can_resume(self):
        self.promoted();save=L.O.save
        def interrupted(path,value):save(path,value);raise PowerLoss()
        with patch.object(L.O,'save',side_effect=interrupted):
            with self.assertRaises(PowerLoss):self.finish()
        self.assertTrue((self.state/'lease.json').exists());self.finish()
        self.assertFalse((self.state/'lease.json').exists())

if __name__=='__main__':unittest.main()
