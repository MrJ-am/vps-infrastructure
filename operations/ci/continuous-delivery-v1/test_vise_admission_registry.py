import copy,sys,unittest
from pathlib import Path
from test_admission_registry import Registry,C,R,path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'vise/delivery'))
import authority_profile as A,source_policy as P

class ViseRegistry(unittest.TestCase):
    def setUp(self):
        self.fixture=Registry();self.fixture.setUp();f=self.fixture
        self.platform_anchor=copy.deepcopy(f.anchor)
        authority=f.docs['authority']
        self.policy={'schema_version':2,'status':'proposed-not-independently-adopted','profile':'vise-v1',
            'rules_revision':authority['rules_revision'],'sources':[{'id':'vise','repository':'MrJ-am/etp-vie-affective',
                'revision':'b'*40,'tree_sha':'c'*40,'root':P.ROOT,'tree_json':P.TREE}],
            'frontends':[],'rust_manifests':{name:'d'*64 for name in P.MANIFESTS},'out_of_scope':P.OUT_OF_SCOPE}
        report=C.canonical(self.policy);f.files[path('report.json')]=report
        authority.update(required_steps=list(A.REQUIRED_STEPS),not_established=list(A.NOT_ESTABLISHED),
            sources=[{k:self.policy['sources'][0][k] for k in ('id','repository','revision','tree_sha')}],
            report_policy_sha256=C.sha(report))
        f.docs['producer']['report_policy_sha256']=C.sha(report)
        authority['producer']=copy.deepcopy(f.docs['producer'])
        self.runtime={n:path(n) for n in ('vise_dependencies','vise_schema','vise_adopt_role',
            'vise_adoption_check','vise_schema_contract','vise_runtime_entry')}
        self.runtime.update(policy=path('report.json'),vise_api_tests=path('api-tests')+'/api-tests.mjs')
        f.files[path('runtime.json')]=C.canonical(self.runtime)
        f.docs['details']={'schema_version':2,'profile':'vise-v1','report_policy':path('report.json'),
            'report_policy_sha256':C.sha(report),'verifier':authority['verifier'],
            'verifier_nar_hash':authority['verifier_nar_hash'],'required_steps':authority['required_steps'],
            'runtime':path('runtime.json'),'runtime_sha256':C.sha(C.canonical(self.runtime))}
        f.refresh();f.anchor=copy.deepcopy(authority)

    def resolve(self,*,profile='vise-v1',anchor=None):
        f=self.fixture
        return R.resolve(f.record,f.proposal,f.anchor if anchor is None else anchor,path('bubblewrap'),
            read=lambda p,maximum=131072:f.files[p],now=150,profile=profile)

    def test_vise_uses_distinct_explicit_anchor(self):
        self.assertEqual(self.resolve()['details']['profile'],'vise-v1')

    def test_vise_document_cannot_select_profile_in_default_reader(self):
        with self.assertRaises(C.Refused):self.resolve(profile='platform')

    def test_platform_anchor_cannot_authorize_vise(self):
        with self.assertRaisesRegex(C.Refused,'ANCHOR_CHANGED'):self.resolve(anchor=self.platform_anchor)

    def test_runtime_candidate_path_refused_even_after_metadata_rehash(self):
        f=self.fixture;self.runtime['vise_runtime_entry']='/input/entry.py'
        raw=C.canonical(self.runtime);f.files[path('runtime.json')]=raw
        f.docs['details']['runtime_sha256']=C.sha(raw);f.refresh()
        with self.assertRaises(C.Refused):self.resolve()

    def test_missing_runtime_check_refused_even_after_metadata_rehash(self):
        f=self.fixture;f.docs['authority']['required_steps'].remove('vise-restore-current-erasure-ledger')
        f.docs['details']['required_steps']=f.docs['authority']['required_steps'];f.refresh()
        with self.assertRaisesRegex(C.Refused,'ANCHOR_CHANGED'):self.resolve()

    def test_overlay_fields_not_silently_accepted_for_vise(self):
        f=self.fixture;f.docs['details']['selected_overlay']='style-logo';f.refresh()
        with self.assertRaises(C.Refused):self.resolve()

if __name__=='__main__':unittest.main()
