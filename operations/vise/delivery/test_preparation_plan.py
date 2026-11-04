import json,sys,unittest
from pathlib import Path
from unittest.mock import patch
import test_host_builder as B
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'ci/authority-v1'))
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'forgejo'))
import preparation_plan as P

class Plan(unittest.TestCase):
    def setUp(self):
        self.builder=B.Builder();self.builder.setUp();self.addCleanup(self.builder.doCleanups)
        self.work=self.builder.work;self.f=self.builder.f
        self.proof=self.builder.run_build()
        self.binding={'source':self.builder.p('source'),'report_policy':self.builder.p('policy'),
            'verification_sha256':'f'*64}
        P.O.save(self.work/'binding.json',self.binding)
        self.job={'id':'d'*64,'phase':'validated','ready':{'base_sha256':'e'*64},
            'capture':{'proposal_sha256':'c'*64,'proposal':{
                'repository':'etp-vie-affective','repository_id':1433178398}}}
        self.f.candidate.update(proposal_sha256='c'*64,binding_sha256=P.C.sha(P.O.encode(self.binding)),
            source=self.binding['source'],policy=self.binding['report_policy'],verification_sha256='f'*64)
        self.ready={**self.proof,'job':self.job['id'],'proposal_sha256':'c'*64,
            'environment_sha256':P.C.sha(P.O.encode(self.f.state)),
            'ready_for_staging':True,'deployment_authorized':False}
        P.O.save(self.work/'ready.json',self.ready)
        self.verify=object()
        for obj,key,value in [(P.D,'vise_binding',None),(P.L,'verify',None),(P.L,'read',None)]:
            p=patch.object(obj,key);m=p.start();self.addCleanup(p.stop)
            if key=='vise_binding':self.bound=m;m.return_value=self.binding
            elif key=='verify':self.layout=m;m.return_value=self.builder.layout.return_value
            else:m.side_effect=lambda path:json.dumps(self.f.candidate).encode()
    def create(self):
        return P.create(self.work,self.work,self.job,self.f.state,self.verify,recipe='/installed/generations.nix')
    def change(self,name,**fields):
        value=json.loads((self.work/name).read_bytes());value.update(fields);P.O.save(self.work/name,value)
    def test_bound_plan_rechecks_signature_and_built_layout_without_authorizing(self):
        plan=self.create()
        self.assertEqual(plan['new'],self.proof['system']);self.assertFalse(plan['deployment_authorized'])
        self.assertEqual(plan['profile'],'vise-v1')
        self.bound.assert_called_once_with(self.work,self.job,self.verify)
        self.layout.assert_called_once()
    def test_expired_signature_cannot_use_saved_success(self):
        self.bound.side_effect=ValueError('expired')
        with self.assertRaisesRegex(ValueError,'expired'):self.create()
        self.layout.assert_not_called()
    def test_swapped_recipe_refused(self):
        self.change('inputs.json',recipe='/candidate/generations.nix')
        with self.assertRaisesRegex(Exception,'VISE_PREPARATION_INPUT_REFUSED'):self.create()
    def test_changed_base_refused(self):
        self.change('input-state.json',system=self.builder.p('other'))
        with self.assertRaisesRegex(Exception,'VISE_PREPARATION_BASE_CHANGED'):self.create()
    def test_changed_verification_artifact_refused(self):
        self.f.candidate['verification_sha256']='a'*64
        with self.assertRaisesRegex(Exception,'VISE_PREPARATION_CANDIDATE_CHANGED'):self.create()
    def test_forged_prepared_success_refused(self):
        self.change('prepared.json',system=self.builder.p('other'))
        with self.assertRaisesRegex(Exception,'VISE_PREPARATION_RECEIPT_CHANGED'):self.create()
    def test_ready_for_another_job_refused(self):
        self.change('ready.json',job='f'*64)
        with self.assertRaisesRegex(Exception,'VISE_PREPARATION_READY_CHANGED'):self.create()
    def test_built_layout_drift_refused(self):
        self.layout.side_effect=ValueError('unsafe layout')
        with self.assertRaisesRegex(ValueError,'unsafe layout'):self.create()
    def test_other_repository_cannot_reuse_vise_preparation(self):
        self.job['capture']['proposal']={'repository':'mrjam-plateforme','repository_id':1437120781}
        with self.assertRaisesRegex(Exception,'VISE_PREPARATION_PROFILE_REFUSED'):self.create()
    def test_reserved_job_refused(self):
        self.job['promotion']={'pending':True}
        with self.assertRaisesRegex(Exception,'VISE_PREPARATION_JOB_REFUSED'):self.create()

if __name__=='__main__':unittest.main()
