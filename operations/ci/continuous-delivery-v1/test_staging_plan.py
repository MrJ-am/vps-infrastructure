import copy,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'authority-v1'))
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'forgejo'))
import test_generation_builder as B
import staging_plan as S

class Plan(unittest.TestCase):
    def setUp(self):
        self.builder=B.Builder();self.builder.setUp();self.addCleanup(self.builder.doCleanups)
        self.work=self.builder.work;self.v=self.builder.fixture;self.proof=self.builder.run_build()
        self.job={'id':'d'*64,'phase':'validated','capture':{'proposal_sha256':'c'*64},'ready':{'base_sha256':'e'*64}}
        self.binding={'source':self.v.p('source'),'report_policy':self.v.p('policy')}
        S.O.save(self.work/'binding.json',self.binding)
        self.v.candidate.update(binding_sha256=S.C.sha(S.O.encode(self.binding)),**self.binding)
        self.v.candidate['policy']=self.v.candidate.pop('report_policy')
        self.ready={**self.proof,'job':self.job['id'],'proposal_sha256':'c'*64,
            'environment_sha256':S.C.sha(S.O.encode(self.v.state)),'ready_for_staging':True,'deployment_authorized':False}
        S.O.save(self.work/'ready.json',self.ready)
        self.authority=True;self.calls=[];self.unit_bad=False;self.built=True
        patcher=patch.object(S.B,'verify');self.layout=patcher.start();self.addCleanup(patcher.stop)
    def create(self):
        def bound(*args):
            self.calls.append('fresh-authority')
            if not self.authority:raise RuntimeError('authority refused')
            return self.binding
        with patch.object(S.D,'binding',side_effect=bound):
            return S.create(self.work,self.work,self.job,self.v.state,object())
    def test_prepared_output_becomes_data_only_bound_plan(self):
        plan=self.create();self.assertEqual(self.calls,['fresh-authority'])
        self.assertEqual(plan['old'],self.v.state);self.assertEqual(plan['staged'],self.proof['stagedState'])
        self.assertEqual(plan['promoted'],self.proof['promotedState']);self.assertEqual(plan['slot'],'green')
        self.assertEqual(plan['preparation_sha256'],S.C.sha(S.O.encode(self.ready)))
    def test_expired_authority_refused_before_plan_creation(self):
        self.authority=False
        with self.assertRaisesRegex(RuntimeError,'authority refused'):self.create()
    def test_ready_receipt_for_another_job_refused(self):
        self.ready['job']='f'*64;S.O.save(self.work/'ready.json',self.ready)
        with self.assertRaisesRegex(Exception,'STAGING_READY_RECEIPT_CHANGED'):self.create()
    def test_preparation_binding_cannot_be_replaced(self):
        S.O.save(self.work/'binding.json',{'source':'other'})
        with self.assertRaisesRegex(Exception,'STAGING_BINDING_CHANGED'):self.create()
    def test_forged_prepared_success_refused(self):
        bad=copy.deepcopy(self.proof);bad['staged']=self.v.p('other-system');S.O.save(self.work/'prepared.json',bad)
        with self.assertRaisesRegex(Exception,'STAGING_PREPARED_RECEIPT_CHANGED'):self.create()
    def test_missing_built_generation_refused(self):
        self.layout.side_effect=RuntimeError('STAGING_GENERATION_NOT_BUILT')
        with self.assertRaisesRegex(Exception,'STAGING_GENERATION_NOT_BUILT'):self.create()
    def test_actual_unit_different_from_evaluated_unit_refused(self):
        self.layout.side_effect=RuntimeError('STAGING_BUILT_UNIT_CHANGED')
        with self.assertRaisesRegex(Exception,'STAGING_BUILT_UNIT_CHANGED'):self.create()

if __name__=='__main__':unittest.main()
