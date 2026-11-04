"""Exercise concrete adapter bindings against the built protected constructor."""
import copy,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import test_intake_queue as T
import test_proposal_prepare as B
import admission_adapter as M
sys.path.insert(0,M.ANCHOR+'/lib')
import contract as C,admission_registry as R,admission_control as A,signer

ROOT=Path(__file__).resolve().parents[3]
LOCAL=ROOT/'.local/deployment-20261101'
BUNDLE='/nix/store/5rxxkx47dqysx35az86nh1kfzzp7bpsj-mrjam-captured-admission'

class ConcreteAdapter(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        request=json.loads((LOCAL/'captured-admission-request-001.json').read_bytes())
        self.path=Path(request['captureRoot']).parent
        capture=json.loads((self.path/'capture/capture.json').read_bytes())
        proposal=capture['proposal'];job={'key':capture['job_key'],'proposal':json.dumps(proposal),
            'receipt':capture['intake_receipt_sha256'],'visible':1}
        self.value={'capture':capture,'bundle':BUNDLE,'validity':{'not_before':request['notBefore'],'expires_at':request['expiresAt']},
            'ready':{'job':job,'result':'a'*64,'base_sha256':capture['base_sha256'],'base_policy_sha256':capture['base_policy_sha256']}}
        self.staged=[]
        self.adapter=M.Adapter(adopted_path='/nix/store/5zc3h26gkpkfqhyvdpsrz1yim6nsmy8v-mrjam-adopted-source.json',
            state=self.root,decisions=self.root/'decisions',recipe='/nix/store/gdsdfskk3a3z52rn0h9921a2x4y6l6bh-mrjam-protected-admission-recipe',
            nix_build='/nonexistent',credentials=None,forge_token='invented-test-token',validator_policy=B.P,gate_path=B.GATE,
            contract=C,registry=R,control=A,signer=signer,stager=SimpleNamespace(reconcile=self.staged.append))
    def test_real_bundle_binds_capture_and_installed_authority(self):
        data=self.adapter.bundle(BUNDLE,self.path,self.value)
        self.assertEqual(data['proposal_sha256'],self.value['capture']['proposal_sha256'])
        self.assertEqual(data['anchor_control'],M.ANCHOR)
        self.assertTrue(self.adapter.current(self.value));self.adapter.check_ready(self.value['ready'])
    def test_capture_sha_cannot_be_swapped(self):
        value=copy.deepcopy(self.value);value['capture']['proposal_sha256']='0'*64
        with self.assertRaisesRegex(M.I.Q.S.Refused,'CONSTRUCTOR_CAPTURE_BINDING'):
            self.adapter.bundle(BUNDLE,self.path,value)
    def test_persisted_validity_cannot_be_swapped(self):
        value=copy.deepcopy(self.value);value['validity']['expires_at']+=1
        with self.assertRaisesRegex(M.I.Q.S.Refused,'CONSTRUCTOR_POLICY_BINDING'):
            self.adapter.bundle(BUNDLE,self.path,value)
    def test_bridge_metadata_must_match_entire_proposal_key(self):
        item=copy.deepcopy(self.value['ready']);proposal=json.loads(item['job']['proposal']);proposal['head']='1'*40
        item['job']['proposal']=json.dumps(proposal)
        with self.assertRaisesRegex(M.I.Q.S.Refused,'READY_JOB_REFUSED'):self.adapter.check_ready(item)
    def test_queued_ci_blocks_staging_before_any_source_is_replaced(self):
        self.adapter.request=lambda *args:{'workflow_runs':[{'id':8,'status':'waiting'}]}
        with self.assertRaisesRegex(M.I.Q.S.Refused,'CI_BUSY'):self.adapter.admit(self.path,self.value)
        self.assertEqual(self.staged,[])
    def test_endpoint_filter_precedes_network_and_disallows_arbitrary_posts(self):
        for method,path,body in [('GET','https://elsewhere.invalid',None),('POST',M.D.BASE+'/issues',{}),
            ('POST',M.D.BASE+'/actions/workflows/independent-validation.yml/dispatches',{'command':'invented'})]:
            with patch.object(M.http.client,'HTTPConnection',side_effect=AssertionError('network must not run')):
                with self.assertRaises((M.I.Q.S.Refused,C.Refused)):self.adapter.request(method,path,body)
    def test_partial_root_copy_is_recovered_without_touching_complete_copy(self):
        partial=self.root/'partial';partial.mkdir(mode=0o700);(partial/'unfinished').write_text('invented')
        self.adapter.recover_partial(partial);self.assertFalse(partial.exists())
        complete=self.root/'complete';complete.mkdir(mode=0o700);(complete/'capture.json').write_text('{}')
        self.adapter.recover_partial(complete);self.assertTrue(complete.exists())
    def test_recovered_source_reobserves_commit_tree(self):
        observed=next(iter(self.value['capture']['observed'].values()))
        with patch.object(M.S,'observe',return_value=observed) as observer:
            result=self.adapter.capture(self.path,self.value)
        self.assertEqual(result,self.value['capture']);observer.assert_called_once()

if __name__=='__main__':unittest.main()
