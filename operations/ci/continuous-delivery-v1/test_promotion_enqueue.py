import copy,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import test_staging_lease as F
import promotion_enqueue as N

class PowerLoss(BaseException):pass

class Enqueue(unittest.TestCase):
    def setUp(self):
        self.f=F.Lease();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.stage=self.f.plan;self.job=self.f.job
        for name in ('old','staged','promoted'):
            self.stage[name]['system']='/nix/store/'+'a'*32+'-nixos-system-'+name
        self.job['capture']['proposal']={'repository':'mrjam-plateforme','head':'a'*40}
        row={'repository':'mrjam-plateforme','head':'a'*40,'number':3,'proposal_sha256':'c'*64}
        self.ledger={'schema_version':1,'job':self.job['id'],'proposal_sha256':'c'*64,
            'receipts':{'mirror':dict(row),'review':{**row,'review_id':9},
                'merge':{**row,'review_id':9,'protected_fast_forward':True,'merger':'mrjam-release-merge'},
                'sync':{'repository':'mrjam-plateforme','head':'a'*40,'canonical_forgejo_main':True,
                    'github_main_synchronized':True,'token_revoked':True}},
            'inflight':None,'next_attempt':0,'attempts':0,'code':None}
        self.plan=N.compose(self.stage,self.job,self.ledger);self.key=N.R.identity(self.plan)['plan_sha256']
        self.state=self.f.state/'promotion';self.state.mkdir(mode=0o700);self.roots=self.f.state/'roots'
        self.events=[];self.now=1000
    def enqueue(self,authorize=None,ready=None):
        return N.enqueue(self.state,self.roots,self.f.jobs,self.plan,
            authorize=authorize or (lambda plan:self.events.append('authority')),
            ready=ready or (lambda:self.events.append('runtime')),
            observe=lambda:(self.plan['old'],)*2,clock=lambda:self.now)
    def test_receipts_create_only_fixed_schema_staged_to_promoted_plan(self):
        self.assertEqual(self.plan['old'],self.stage['staged']['system'])
        self.assertEqual(self.plan['new'],self.stage['promoted']['system'])
        self.assertEqual(set(self.plan),{'schema_version','job','proposal_sha256','old','new','slot','bundle','forge_pull','review'})
    def test_missing_sync_or_wrong_head_cannot_enqueue(self):
        self.ledger['receipts'].pop('sync')
        with self.assertRaisesRegex(Exception,'ENQUEUE_ACCEPTANCE_INCOMPLETE'):N.compose(self.stage,self.job,self.ledger)
        self.ledger['receipts']['sync']={'repository':'wrong','head':'b'*40}
        with self.assertRaisesRegex(Exception,'ENQUEUE_SOURCE_RECEIPT_CHANGED'):N.compose(self.stage,self.job,self.ledger)
    def test_readiness_rechecked_after_fresh_authority_before_plan_published(self):
        self.assertEqual(self.enqueue()['code'],'PROMOTION_PLAN_ENQUEUED')
        self.assertEqual(self.events,['runtime','authority','runtime'])
        self.assertEqual(N.L.read(self.state/'plan.json'),self.plan)
        self.assertEqual(str((self.roots/(self.key+'-old')).readlink()),self.plan['old'])
    def test_invalid_authority_never_writes_plan_or_roots(self):
        def refused(plan):raise RuntimeError('expired')
        with self.assertRaisesRegex(RuntimeError,'expired'):self.enqueue(authorize=refused)
        self.assertFalse((self.state/'plan.json').exists());self.assertFalse(self.roots.exists())
    def test_lost_ack_after_plan_write_resumes_identical_plan(self):
        save=N.O.save
        def interrupted(path,value):save(path,value);raise PowerLoss()
        with patch.object(N.O,'save',side_effect=interrupted):
            with self.assertRaises(PowerLoss):self.enqueue()
        self.assertEqual(self.enqueue()['code'],'PROMOTION_PLAN_PRESENT')
        self.assertEqual(N.L.read(self.state/'plan.json'),self.plan)
    def test_unfinished_previous_plan_cannot_be_overwritten(self):
        previous={**self.plan,'forge_pull':4};N.O.save(self.state/'plan.json',previous)
        with self.assertRaises(Exception):self.enqueue()
        self.assertEqual(N.L.read(self.state/'plan.json'),previous)
    def test_completed_previous_plan_requires_matching_job_receipt(self):
        previous={**self.plan,'job':'b'*64,'forge_pull':4};key=N.R.identity(previous)['plan_sha256']
        N.O.save(self.state/'plan.json',previous)
        N.O.save(self.state/(key+'.json'),{'schema_version':1,'plan_sha256':key,'phase':'complete'})
        job=copy.deepcopy(self.job);job.update(id='b'*64,phase='deployed',delivery={
            'plan_sha256':key,'proposal_sha256':previous['proposal_sha256'],'generation':previous['new'],
            'previous_generation':previous['old']})
        path=self.f.jobs/job['id'];path.mkdir(mode=0o700);N.O.save(path/'state.json',job)
        self.assertEqual(self.enqueue()['code'],'PROMOTION_PLAN_ENQUEUED')
    def failed(self):
        self.enqueue();N.O.save(self.state/(self.key+'.json'),{'schema_version':1,'plan_sha256':self.key,'phase':'failed'})
        self.job['delivery_return']={'plan_sha256':self.key,'generation':self.plan['old']}
        N.O.save(self.f.jobs/self.job['id']/'state.json',self.job)
    def previous_vise_return(self):
        previous={**self.plan,'job':'b'*64,'profile':'vise-v1'}
        key=N.R.identity(previous)['plan_sha256']
        N.O.save(self.state/'plan.json',previous)
        N.O.save(self.state/(key+'.json'),{'schema_version':1,'plan_sha256':key,'phase':'failed'})
        job=copy.deepcopy(self.job);job['id']=previous['job']
        job['delivery_return']={'plan_sha256':key,'generation':previous['old']}
        path=self.f.jobs/job['id'];path.mkdir(mode=0o700);N.O.save(path/'state.json',job)
        return previous,key,job,path
    def test_proven_vise_return_allows_other_project_without_erasing_history(self):
        previous,key,job,path=self.previous_vise_return()
        self.assertEqual(self.enqueue()['code'],'PROMOTION_PLAN_ENQUEUED')
        self.assertEqual(N.L.read(self.state/'plan.json'),self.plan)
        self.assertEqual(N.L.read(self.state/(key+'.json'))['phase'],'failed')
        self.assertEqual(N.O.read(path/'state.json'),job)
    def test_vise_return_does_not_bypass_new_authority(self):
        previous,key,job,path=self.previous_vise_return()
        def refused(plan):raise RuntimeError('expired')
        with self.assertRaisesRegex(RuntimeError,'expired'):self.enqueue(authorize=refused)
        self.assertEqual(N.L.read(self.state/'plan.json'),previous)
    def test_incomplete_or_conflicting_vise_return_blocks_replacement(self):
        previous,key,job,path=self.previous_vise_return()
        for change in ({'delivery_return':None},{'delivery_return':{'plan_sha256':'0'*64,'generation':previous['old']}},
                {'promotion':N.R.identity(previous)},{'phase':'deployed'},{'delivery':{'unexpected':True}}):
            with self.subTest(change=change):
                N.O.save(path/'state.json',{**job,**change})
                with self.assertRaises(Exception):self.enqueue()
                self.assertEqual(N.L.read(self.state/'plan.json'),previous)
        N.O.save(path/'state.json',job)
        N.O.save(self.state/(key+'.json'),{'schema_version':1,'plan_sha256':key,'phase':'recovering'})
        with self.assertRaisesRegex(Exception,'ENQUEUE_PREVIOUS_PROMOTION_PENDING'):self.enqueue()
    def test_retry_requires_proven_return_and_retains_failure_record(self):
        self.failed();self.assertEqual(self.enqueue()['code'],'PROMOTION_PLAN_PRESENT')
        self.assertEqual(N.L.read(self.state/(self.key+'.json'))['phase'],'prepared')
        self.assertEqual(N.L.read(self.state/('last-failure-'+self.key+'.json'))['phase'],'failed')
        N.O.save(self.state/(self.key+'.json'),{'schema_version':1,'plan_sha256':self.key,'phase':'failed'})
        self.assertEqual(self.enqueue()['code'],'PROMOTION_RETRY_WAIT')
    def test_unproven_return_cannot_reset_failed_promotion(self):
        self.failed();self.job.pop('delivery_return');N.O.save(self.f.jobs/self.job['id']/'state.json',self.job)
        with self.assertRaisesRegex(Exception,'ENQUEUE_FAILED_RETURN_UNPROVEN'):self.enqueue()
    def test_recovery_required_is_never_erased(self):
        self.enqueue();N.O.save(self.state/(self.key+'.json'),{'schema_version':1,'plan_sha256':self.key,'phase':'recovery-required'})
        with self.assertRaisesRegex(Exception,'ENQUEUE_PROMOTION_REQUIRES_RECOVERY'):self.enqueue()

if __name__=='__main__':unittest.main()
