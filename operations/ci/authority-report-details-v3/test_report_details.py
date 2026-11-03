"""Consume the existing report; invented key/receipt, no application rerun."""
import ast,base64,copy,hashlib,importlib.util,json,os,socket,subprocess,sys,threading,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
RUN=ROOT/'.local/ci-current-validator-v1-20261103/native-validation-001'
PACKAGE=Path('/nix/store/cqz4jlhpis05gj4wcjgaddb45qbfwpz0-mrjam-validation-authority-report-details-3')
OLD=Path('/nix/store/19r3a6ylzp32vg3bkfr9wfhd1n8cwm71-mrjam-validation-authority-credentials-2')
sys.path.insert(0,str(PACKAGE/'lib'))
import contract as C,signer as A,client as V,report_details as D
spec=importlib.util.spec_from_file_location('old_signer',OLD/'lib/signer.py');OLD_A=importlib.util.module_from_spec(spec);spec.loader.exec_module(OLD_A)

class ReportDetailsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result_raw=(RUN/'result.json').read_bytes();cls.raw=(RUN/'artifacts/verification.json').read_bytes()
        assert C.sha(cls.result_raw)=='8dd98924157d1a42c2b727b97eb0f291131f9a16a1a8b245d0743cad16135585'
        assert C.sha(cls.raw)=='92d4468cbab1dd20f38fee9d16390c7ab0ed4a8c28dbc16aea3e4a8e6fee760d'
        cls.report=C.parse(cls.raw);cls.proposal=cls.report['proposal_sha256']
        cls.policy=C.parse(Path(A.POLICY_PATH).read_bytes())
        cls.artifacts=[]
        for name,limit in C.ARTIFACTS:
            data=(RUN/'artifacts'/name).read_bytes();assert 0<len(data)<=limit
            cls.artifacts.append({'name':name,'bytes':len(data),'sha256':C.sha(data)})
        cls.receipt={'schema_version':2,'decision':'passed','proposal_sha256':cls.proposal,'rules_revision':cls.policy['rules_revision'],'artifacts':cls.artifacts,'authority':'bound-local-controller-receipt','producer':cls.policy['producer']}
        # Only this freshly invented private key is read into Python memory.
        cls.key=subprocess.check_output([A.OPENSSL,'genpkey','-algorithm','ED25519'],stderr=subprocess.DEVNULL)
        fd=C.memfd(cls.key)
        try:public=A.openssl(['pkey','-in','/proc/self/fd/'+str(fd),'-pubout','-outform','DER'],[fd])
        finally:os.close(fd)
        cls.synthetic={**cls.policy,'key_id':C.sha(public),'public_key_der':base64.b64encode(public).decode(),'signer_uid':os.getuid(),'collector_uid':os.getuid()+1,'requester_uid':os.getuid()+2}
        cls.now=cls.synthetic['not_before']+60
    @classmethod
    def tearDownClass(cls):
        assert (RUN/'result.json').read_bytes()==cls.result_raw
        assert (RUN/'artifacts/verification.json').read_bytes()==cls.raw
    def check(self,report=None,policy=None):
        return A.check_report(self.report if report is None else report,self.receipt,self.proposal,self.policy if policy is None else policy)
    def test_01_old_consumer_refuses_original_report(self):
        with self.assertRaisesRegex(C.Refused,'REQUIRED_STEPS_REFUSED'):OLD_A.check_report(self.report,self.receipt,self.proposal,self.policy)
    def test_02_new_consumer_accepts_original_report_exactly(self):
        self.check();self.assertEqual(len(self.report['steps']),75)
        self.assertEqual([x for x in self.report['steps'] if set(x)!={'name','status'}],[D.expected_steps(self.policy)[self.policy['required_steps'].index('explicit-manifest-overlay-style-logo')]])
        self.assertEqual(self.report['artifacts'],self.artifacts[:2])
    def test_03_each_wrong_or_missing_digest_refused(self):
        for field in ('base_sha256','corrected_sha256'):
            for remove in (False,True):
                report=copy.deepcopy(self.report);entry=next(x for x in report['steps'] if x['name']=='explicit-manifest-overlay-style-logo')
                if remove:del entry[field]
                else:entry[field]='0'*64
                with self.subTest(field=field,remove=remove),self.assertRaisesRegex(C.Refused,'REQUIRED_STEPS_REFUSED'):self.check(report)
    def test_04_unknown_fields_and_other_detailed_steps_refused(self):
        for index in (0,self.policy['required_steps'].index('explicit-manifest-overlay-style-logo')):
            report=copy.deepcopy(self.report);report['steps'][index]['extra']='unexpected'
            with self.subTest(index=index),self.assertRaisesRegex(C.Refused,'REQUIRED_STEPS_REFUSED'):self.check(report)
    def test_05_step_order_omission_and_status_refused(self):
        for case in ('order','omit','failed'):
            report=copy.deepcopy(self.report)
            if case=='order':report['steps'][0:2]=reversed(report['steps'][0:2])
            elif case=='omit':report['steps'].pop()
            else:report['steps'][0]['status']='failed'
            with self.subTest(case=case),self.assertRaisesRegex(C.Refused,'REQUIRED_STEPS_REFUSED'):self.check(report)
    def test_06_descriptor_rejects_different_policy_verifier_nar_or_names(self):
        for field,value in [('report_policy_sha256','0'*64),('verifier','/nix/store/'+'0'*32+'-other'),('verifier_nar_hash','sha256-'+base64.b64encode(b'x'*32).decode()),('required_steps',self.policy['required_steps'][:-1])]:
            with self.subTest(field=field),self.assertRaisesRegex(C.Refused,'REPORT_DETAILS_BINDING_REFUSED'):D.expected_steps({**self.policy,field:value})
    def test_07_remaining_report_guards_preserved(self):
        for field,value in [('sources',[]),('production_authorized',True),('independent_adoption_established',True),('not_established',[]),('artifacts',[])]:
            with self.subTest(field=field),self.assertRaises(C.Refused):self.check({**self.report,field:value})
    def test_08_synthetic_signature_verifies_with_old_unchanged_verifier(self):
        envelope=A.attest(self.receipt,self.report,self.proposal,self.synthetic,self.key,now=self.now)
        self.assertTrue(OLD_A.verify(envelope,self.synthetic,now=self.now))
        self.assertEqual(envelope['payload']['steps'],[{'name':name,'status':'passed'} for name in self.policy['required_steps']])
        self.assertEqual(envelope['payload']['artifacts'][2],{'name':'verification.json','bytes':6652,'sha256':C.sha(self.raw)})
        wrong=copy.deepcopy(envelope);wrong['payload']['steps']=self.report['steps']
        with self.assertRaises(C.Refused):OLD_A.verify(wrong,self.synthetic,now=self.now)
    def test_09_unchanged_client_accepts_real_unix_exchange(self):
        envelope=A.attest(self.receipt,self.report,self.proposal,self.synthetic,self.key,now=self.now)
        left,right=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET);errors=[]
        def reply():
            try:
                with right:
                    assert C.request(right,end=time.monotonic()+3)==self.proposal
                    C.send_packet(right,C.canonical(envelope),[],end=time.monotonic()+3)
            except BaseException as error:errors.append(type(error).__name__)
        thread=threading.Thread(target=reply);thread.start()
        try:
            with left:self.assertEqual(V.receive(left,self.proposal,self.synthetic,now=self.now,end=time.monotonic()+3),envelope)
        finally:thread.join(4)
        self.assertFalse(thread.is_alive());self.assertEqual(errors,[])
    def test_10_only_two_signer_functions_changed(self):
        old=ast.parse((OLD/'lib/signer.py').read_bytes());new=ast.parse((PACKAGE/'lib/signer.py').read_bytes())
        functions=lambda tree:{n.name:ast.dump(n,include_attributes=False) for n in tree.body if isinstance(n,ast.FunctionDef)}
        before,after=functions(old),functions(new);self.assertEqual(set(before),set(after))
        self.assertEqual({k for k in before if before[k]!=after[k]},{'attest','check_report'})
        for name in ('client.py','contract.py','producer.py','collector.py','exporter.py','frozen_worker.py','signing_credential.py'):
            with self.subTest(name=name):self.assertEqual((OLD/'lib'/name).read_bytes(),(PACKAGE/'lib'/name).read_bytes())
    def test_11_descriptor_links_existing_immutable_inputs(self):
        d=D.descriptor();self.assertEqual(d,json.loads((HERE/'descriptor.json').read_bytes()))
        for path,digest in [('report_policy','report_policy_sha256'),('runtime','runtime_sha256'),('overlay_manifest','overlay_manifest_sha256')]:self.assertEqual(C.sha(Path(d[path]).read_bytes()),d[digest])
        manifest=json.loads(Path(d['overlay_manifest']).read_bytes());self.assertEqual([x for x in manifest['overlays'] if x['case']=='style-logo'],[d['selected_entry']])
        info=json.loads(subprocess.check_output(['nix','--extra-experimental-features','nix-command','path-info','--json',d['verifier']],stderr=subprocess.DEVNULL));info=info[d['verifier']] if isinstance(info,dict) else info[0]
        self.assertEqual(info['narHash'],d['verifier_nar_hash'])
    def test_12_original_global_failure_and_artifacts_remain_unchanged(self):
        self.assertEqual(json.loads(self.result_raw)['status'],'failed')
        observation=json.loads((RUN/'application-observation-001.json').read_bytes())
        self.assertEqual(self.artifacts,observation['artifacts']);self.assertFalse(observation['application_validation_repeated'])

if __name__=='__main__':unittest.main(verbosity=2)
