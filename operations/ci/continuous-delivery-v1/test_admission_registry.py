import copy,importlib.util,json,os,sys,tempfile,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('contract',HERE.parent/'authority-v1/contract.py')
C=importlib.util.module_from_spec(spec);sys.modules['contract']=C;spec.loader.exec_module(C)
import admission_registry as R

def path(name):return '/nix/store/'+'a'*32+'-'+name

class Registry(unittest.TestCase):
    def setUp(self):
        self.proposal='1'*64
        authority=json.loads(Path('/nix/store/d8bhnl18vsch1zbrvm28w6dvn6acz1k6-mrjam-validation-authority-policy.json').read_bytes())
        details=json.loads(Path('/nix/store/fdxh1p60i5bdspiqjid5wjv52k9r4scr-mrjam-authority-report-details-v3.json').read_bytes())
        report={'rules_revision':authority['rules_revision'],'sources':authority['sources'],
                'frontends':[{'id':'style-logo','manifest_overlay':'style-logo'}]}
        closure=(authority['verifier']+'\n').encode()
        worker={'schema_version':1,'rules_revision':authority['rules_revision'],
                'validator_store':authority['verifier'],'bubblewrap_store':path('bubblewrap'),
                'closure_file':path('closure')+'/store-paths'}
        producer=copy.deepcopy(authority['producer'])
        producer.update(worker_policy_sha256=C.sha(C.canonical(worker)),closure_sha256=C.sha(closure),
                        report_policy_sha256=C.sha(C.canonical(report)))
        authority.update(producer=producer,closure_sha256=producer['closure_sha256'],
                         report_policy_sha256=producer['report_policy_sha256'],
                         accepted_proposals=[self.proposal],not_before=100,expires_at=200)
        details.update(report_policy=path('report.json'),report_policy_sha256=producer['report_policy_sha256'])
        runtime=C.canonical({'policy':path('report.json'),'manifest_overlays':path('overlays')})
        overlay=C.canonical({'overlays':[details['selected_entry']]})
        details.update(runtime=path('runtime.json'),runtime_sha256=C.sha(runtime),
                       overlay_manifest=path('overlays')+'/manifest.json',overlay_manifest_sha256=C.sha(overlay))
        self.docs={'authority':authority,'producer':producer,'worker':worker,'details':details}
        self.files={worker['closure_file']:closure,path('report.json'):C.canonical(report)}
        self.files.update({path('runtime.json'):runtime,path('overlays')+'/manifest.json':overlay})
        self.record={'schema_version':1,'proposal_sha256':self.proposal,'files':{}}
        self.refresh()
        self.anchor=copy.deepcopy(authority)

    def refresh(self):
        for name,document in self.docs.items():
            raw=C.canonical(document);target=path(name+'.json');self.files[target]=raw
            self.record['files'][name]={'path':target,'sha256':C.sha(raw)}

    def resolve(self,now=150):
        return R.resolve(self.record,self.proposal,self.anchor,path('bubblewrap'),
                         read=lambda p,maximum=131072:self.files[p],now=now)

    def test_exact_bound_record(self):
        result=self.resolve()
        self.assertEqual(result['authority']['accepted_proposals'],[self.proposal])

    def test_unlisted_proposal_and_expiry(self):
        with self.assertRaises(C.Refused):self.resolve(now=200)
        self.docs['authority']['accepted_proposals']=['2'*64];self.refresh()
        with self.assertRaises(C.Refused):self.resolve()

    def test_changed_signer_identity_refused_even_if_record_rehashed(self):
        self.docs['authority']['signer_uid']=12345;self.refresh()
        with self.assertRaisesRegex(C.Refused,'ANCHOR_CHANGED'):self.resolve()

    def test_removed_required_test_refused_even_if_record_rehashed(self):
        self.docs['authority']['required_steps'].pop()
        self.docs['details']['required_steps']=self.docs['authority']['required_steps']
        self.refresh()
        with self.assertRaisesRegex(C.Refused,'ANCHOR_CHANGED'):self.resolve()

    def test_worker_switch_refused(self):
        self.docs['worker']['validator_store']=path('other-verifier')
        self.docs['producer']['worker_policy_sha256']=C.sha(C.canonical(self.docs['worker']))
        self.refresh()
        with self.assertRaisesRegex(C.Refused,'WORKER_REFUSED'):self.resolve()

    def test_changed_document_or_closure_refused(self):
        target=self.record['files']['worker']['path'];original=self.files[target]
        self.files[target]=original+b' '
        with self.assertRaisesRegex(C.Refused,'CONTENT_CHANGED'):self.resolve()
        self.files[target]=original
        self.files[self.docs['worker']['closure_file']]+=b'changed\n'
        with self.assertRaisesRegex(C.Refused,'CLOSURE_REFUSED'):self.resolve()

    def test_native_registry_metadata_and_symlink_refusals(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary);candidate=directory/(self.proposal+'.json')
            candidate.write_bytes(C.canonical(self.record));candidate.chmod(0o444)
            self.assertEqual(R.entry(self.proposal,directory=directory,owner=os.getuid()),self.record)
            candidate.chmod(0o644)
            with self.assertRaises(C.Refused):R.entry(self.proposal,directory=directory,owner=os.getuid())
            candidate.chmod(0o444)
            directory.chmod(0o777)
            with self.assertRaises(C.Refused):R.entry(self.proposal,directory=directory,owner=os.getuid())
            directory.chmod(0o700)
            original=directory/'original';candidate.rename(original);candidate.symlink_to(original)
            with self.assertRaises(OSError):R.entry(self.proposal,directory=directory,owner=os.getuid())

    def test_runtime_and_overlay_substitution_refused(self):
        target=path('runtime.json');original=self.files[target]
        self.files[target]=b'{}'
        with self.assertRaisesRegex(C.Refused,'RUNTIME_REFUSED'):self.resolve()
        self.files[target]=original
        self.docs['details']['selected_entry']['corrected_sha256']='0'*64;self.refresh()
        with self.assertRaisesRegex(C.Refused,'OVERLAY_REFUSED'):self.resolve()

if __name__=='__main__':unittest.main()
