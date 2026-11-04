"""Real Ed25519, invented artifacts/key; registry lookup substituted explicitly.

Root filesystem ownership and revocation are exercised separately in the VM.
This suite does not claim compilation or production signing.
"""
import base64,copy,json,os,subprocess,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch

PACKAGE=Path(os.environ.get('MRJAM_ADMISSION_TEST_PACKAGE','/nix/store/7hpx8az4rb1cvilj2nvvflsh1gbr1nf1-mrjam-validation-admission-control-1'))
sys.path.insert(0,str(PACKAGE/'lib'))
import contract as C
import signer as A
import admission_control as R

class Signing(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        keyfile=Path(self.temp.name)/'invented.key'
        subprocess.run([A.OPENSSL,'genpkey','-algorithm','ED25519','-out',str(keyfile)],
                       stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
        keyfile.chmod(0o400);self.key=keyfile.read_bytes()
        public=subprocess.check_output([A.OPENSSL,'pkey','-in',str(keyfile),'-pubout','-outform','DER'],stderr=subprocess.DEVNULL)
        self.proposal='a'*64
        self.policy=C.parse(Path(R.ANCHOR_PATH).read_bytes())
        self.policy.update(key_id=C.sha(public),public_key_der=base64.b64encode(public).decode(),
                           accepted_proposals=[self.proposal],not_before=int(time.time())-60,
                           expires_at=int(time.time())+120)
        self.details=json.loads(Path('/nix/store/fdxh1p60i5bdspiqjid5wjv52k9r4scr-mrjam-authority-report-details-v3.json').read_bytes())
        self.entries={self.proposal:{'authority':self.policy,'details':self.details}}
        def lookup(proposal):
            C.require(proposal in self.entries,'TEST_ADMISSION_ABSENT')
            return self.entries[proposal]
        self.patch=patch.object(R,'load',side_effect=lookup);self.patch.start()
        self.bodies=[b'invented executable fixture',b'invented frontend fixture']
        artifacts=[{'name':name,'bytes':len(raw),'sha256':C.sha(raw)}
                   for name,raw in zip(('server','frontend.tar'),self.bodies)]
        self.report={'schema_version':1,'decision':'passed','authority':'local-verifier-content-receipt',
                     'independent_adoption_established':False,'production_authorized':False,
                     'proposal_sha256':self.proposal,'rules_revision':self.policy['rules_revision'],
                     'policy_sha256':self.policy['report_policy_sha256'],'steps':R.expected_steps(self.policy),
                     'sources':self.policy['sources'],'artifacts':artifacts,'not_established':self.policy['not_established']}
        report_raw=C.canonical(self.report)
        self.receipt={'schema_version':2,'decision':'passed','proposal_sha256':self.proposal,
                      'rules_revision':self.policy['rules_revision'],'artifacts':artifacts+[
                          {'name':'verification.json','bytes':len(report_raw),'sha256':C.sha(report_raw)}],
                      'authority':'bound-local-controller-receipt','producer':self.policy['producer']}

    def tearDown(self):
        self.patch.stop();self.temp.cleanup()

    def attest(self,report=None,policy=None):
        return A.attest(self.receipt,report or self.report,self.proposal,policy or self.policy,self.key)

    def test_actual_signature_and_exact_detailed_report(self):
        envelope=self.attest()
        self.assertTrue(A.verify(envelope,self.policy))
        self.assertNotIn(self.key.decode(),json.dumps(envelope))
        self.assertEqual(len(envelope['payload']['steps']),74)

    def test_removed_admission_prevents_attestation(self):
        self.entries.clear()
        with self.assertRaisesRegex(C.Refused,'TEST_ADMISSION_ABSENT'):self.attest()

    def test_replaced_admission_prevents_stale_attestation(self):
        changed=copy.deepcopy(self.policy);changed['expires_at']+=1
        self.entries[self.proposal]['authority']=changed
        with self.assertRaisesRegex(C.Refused,'ADMISSION_CHANGED'):self.attest()

    def test_forged_overlay_detail_and_source_refused(self):
        report=copy.deepcopy(self.report)
        next(s for s in report['steps'] if 'base_sha256' in s)['base_sha256']='0'*64
        with self.assertRaisesRegex(C.Refused,'REQUIRED_STEPS_REFUSED'):self.attest(report=report)
        report=copy.deepcopy(self.report);report['sources'][0]['revision']='0'*40
        with self.assertRaisesRegex(C.Refused,'SOURCE_BINDING_REFUSED'):self.attest(report=report)

    def test_signature_not_reusable_for_another_admitted_digest(self):
        envelope=self.attest()
        other=copy.deepcopy(self.policy);other['accepted_proposals']=['b'*64]
        with self.assertRaises(C.Refused):A.verify(envelope,other)
        changed=copy.deepcopy(envelope);changed['payload']['proposal_sha256']='b'*64
        with self.assertRaises(C.Refused):A.verify(changed,other)

    def test_expired_admission_refused(self):
        expired=copy.deepcopy(self.policy);expired['expires_at']=int(time.time())-1
        with self.assertRaisesRegex(C.Refused,'POLICY_EXPIRED'):self.attest(policy=expired)

if __name__=='__main__':unittest.main()
