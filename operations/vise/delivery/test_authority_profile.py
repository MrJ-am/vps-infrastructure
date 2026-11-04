import copy,hashlib,importlib.util,json,unittest
from pathlib import Path
import authority_profile as A,source_policy as P

path=Path(__file__).resolve().parents[2]/'ci/authority-v1/contract.py'
spec=importlib.util.spec_from_file_location('vise_authority_contract_fixture',path)
C=importlib.util.module_from_spec(spec);spec.loader.exec_module(C)

class AuthorityProfile(unittest.TestCase):
    def setUp(self):
        self.report={'schema_version':2,'status':'proposed-not-independently-adopted','profile':'vise-v1',
            'rules_revision':'a'*40,'sources':[{'id':'vise','repository':'MrJ-am/etp-vie-affective',
                'revision':'b'*40,'tree_sha':'c'*40,'root':P.ROOT,'tree_json':P.TREE}],
            'frontends':[],'rust_manifests':{name:'d'*64 for name in P.MANIFESTS},'out_of_scope':P.OUT_OF_SCOPE}
        self.raw=json.dumps(self.report,sort_keys=True).encode()
        # Public policy metadata only; no private signing credential is read.
        self.authority=json.loads(Path('/nix/store/d8bhnl18vsch1zbrvm28w6dvn6acz1k6-mrjam-validation-authority-policy.json').read_bytes())
        self.authority.update(rules_revision='a'*40,report_policy_sha256=hashlib.sha256(self.raw).hexdigest(),
            required_steps=list(A.REQUIRED_STEPS),not_established=list(A.NOT_ESTABLISHED),
            sources=[{k:self.report['sources'][0][k] for k in ['id','repository','revision','tree_sha']}])
        self.authority['producer'].update(rules_revision='a'*40,report_policy_sha256=self.authority['report_policy_sha256'])
    def verify(self,**kwargs):
        return A.expected_steps(self.authority,kwargs.get('raw',self.raw),contract=C,rules_revision=kwargs.get('rules','a'*40))
    def test_profile_binds_real_authority_contract_without_platform_overlay(self):
        steps=self.verify()
        self.assertEqual([s['name'] for s in steps],list(A.REQUIRED_STEPS))
        self.assertTrue(all(set(s)=={'name','status'} for s in steps))
    def test_missing_or_platform_step_is_refused(self):
        for steps in [list(A.REQUIRED_STEPS[:-1]),list(A.REQUIRED_STEPS)+['explicit-manifest-overlay-style-logo']]:
            with self.subTest(steps=steps),self.assertRaisesRegex(P.Refused,'STEPS_REFUSED'):
                self.authority['required_steps']=steps;self.verify()
    def test_new_report_bytes_cannot_reuse_existing_authority_binding(self):
        other=copy.deepcopy(self.report);other['sources'][0]['revision']='e'*40
        with self.assertRaisesRegex(P.Refused,'POLICY_BINDING_REFUSED'):
            self.verify(raw=json.dumps(other,sort_keys=True).encode())
    def test_source_switch_is_refused_even_with_same_steps(self):
        self.authority['sources'][0]['repository']='MrJ-am/mrjam-plateforme'
        with self.assertRaisesRegex(P.Refused,'SOURCE_BINDING_REFUSED'):self.verify()
    def test_rules_cannot_be_selected_by_candidate(self):
        with self.assertRaisesRegex(P.Refused,'RULES_REFUSED'):self.verify(rules='f'*40)
    def test_limits_cannot_be_dropped_to_claim_production_authority(self):
        self.authority['not_established']=['Deployment is authorized.']
        with self.assertRaisesRegex(P.Refused,'LIMITS_REFUSED'):self.verify()

if __name__=='__main__':unittest.main()
