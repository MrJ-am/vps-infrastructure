"""Local cryptographic/Unix tests with invented keys and code payloads only."""
import base64,copy,fcntl,hashlib,importlib.util,json,os,socket,subprocess,sys,tempfile,threading,time,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
spec=importlib.util.spec_from_file_location('frozen_submit',ROOT/'operations/forgejo/submit.py');S=importlib.util.module_from_spec(spec);spec.loader.exec_module(S);sys.modules['frozen_submit']=S
spec=importlib.util.spec_from_file_location('frozen_worker',ROOT/'operations/forgejo/worker.py');W=importlib.util.module_from_spec(spec);spec.loader.exec_module(W);sys.modules['frozen_worker']=W
sys.path.insert(0,str(HERE));import contract as C;import exporter as E;import signer as A;import producer as P;import collector as K;import client as V
OPENSSL='/nix/store/fya253x5ky7rhfz6rkgdwjr1fzf7fy71-openssl-3.6.5-bin/bin/openssl'

class AuthorityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='mrjam-authority-synthetic-');self.root=Path(self.temp.name);self.cache=self.root/'cache';self.cache.mkdir(mode=0o700)
        self.key=subprocess.check_output([OPENSSL,'genpkey','-algorithm','ED25519'],stderr=subprocess.DEVNULL)
        keyfile=self.root/'key';keyfile.write_bytes(self.key);keyfile.chmod(0o400)
        public=subprocess.check_output([OPENSSL,'pkey','-in',str(keyfile),'-pubout','-outform','DER'],stderr=subprocess.DEVNULL)
        self.proposal='a'*64;self.rules='b'*40;now=int(time.time())
        self.policy={'schema_version':1,'scope':'mrjam-validation-content-authority-v1','rules_revision':self.rules,'verifier':'/nix/store/'+'0'*32+'-synthetic-verifier','verifier_nar_hash':'sha256-'+base64.b64encode(b'v'*32).decode(),'closure_sha256':'c'*64,'report_policy_sha256':'d'*64,'collector_uid':os.getuid(),'signer_uid':os.getuid()+1,'requester_uid':os.getuid()+2,'key_id':C.sha(public),'public_key_der':base64.b64encode(public).decode(),'not_before':now-60,'expires_at':now+60,'required_steps':['synthetic-code-contract'],'sources':[{'id':'synthetic','repository':'invented/code','revision':'e'*40,'tree_sha':'f'*40}],'accepted_proposals':[self.proposal],'not_established':['production activation','human review']}
        self.binding={'schema_version':1,**{k:self.policy[k] for k in ['rules_revision','verifier','verifier_nar_hash','closure_sha256','report_policy_sha256']},'worker_policy_sha256':'1'*64,'producer_recipe_sha256':C.sha((HERE/'producer.py').read_bytes()),'worker_core_sha256':C.sha((ROOT/'operations/forgejo/worker.py').read_bytes()),'collector_recipe_sha256':C.sha((HERE/'collector.py').read_bytes()),'contract_sha256':C.sha((HERE/'contract.py').read_bytes())}
        self.policy['producer']=self.binding
        self.bodies=[b'invented executable code',b'invented frontend code']
        entries=[{'name':name,'bytes':len(raw),'sha256':C.sha(raw)} for (name,_),raw in zip(C.ARTIFACTS,self.bodies)]
        self.report={'schema_version':1,'decision':'passed','authority':'local-verifier-content-receipt','independent_adoption_established':False,'production_authorized':False,'proposal_sha256':self.proposal,'rules_revision':self.rules,'policy_sha256':self.policy['report_policy_sha256'],'steps':[{'name':'synthetic-code-contract','status':'passed'}],'sources':self.policy['sources'],'artifacts':entries,'not_established':self.policy['not_established']}
        self.bodies.append(C.canonical(self.report))
        self.receipt={'schema_version':2,'decision':'passed','proposal_sha256':self.proposal,'rules_revision':self.rules,'artifacts':[{'name':name,'bytes':len(raw),'sha256':C.sha(raw)} for (name,_),raw in zip(C.ARTIFACTS,self.bodies)],'authority':'bound-local-controller-receipt','producer':self.binding}
        directory=self.cache/self.proposal;directory.mkdir(mode=0o700)
        for entry,raw in zip(self.receipt['artifacts'],self.bodies):
            p=directory/entry['name'];p.write_bytes(raw);p.chmod(0o400)
        p=directory/'receipt.json';p.write_bytes(C.canonical(self.receipt));p.chmod(0o400)
        p=self.cache/'.collection.lock';p.touch(mode=0o600)
        # A single local test UID exercises real kernel credentials; the unit's
        # distinct service identities need the separately scheduled systemd VM.
        self.export_policy={'schema_version':1,'rules_revision':self.rules,'requester_uid':os.getuid(),'producer':self.binding}
    def tearDown(self):self.temp.cleanup()
    def pair(self):return socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)
    def export(self,policy=None,raw=None):
        left,right=self.pair();status=[]
        thread=threading.Thread(target=lambda:status.append(E.serve(right,policy or self.export_policy,str(self.cache),budget=1)))
        thread.start()
        try:
            if raw is None:receipt,report=A.receive_export(left,self.proposal,self.policy,end=time.monotonic()+2);return receipt,report
            left.sendall(raw);left.shutdown(socket.SHUT_WR);data,fds=C.packet(left,4096,end=time.monotonic()+2);C.close_fds(fds);return C.parse(data)
        finally:left.close();thread.join(3);right.close();self.assertFalse(thread.is_alive())
    def test_real_unix_credentials_three_sealed_fds_and_signature(self):
        receipt,report=self.export();self.assertEqual(receipt,self.receipt);self.assertEqual(report,self.report)
        envelope=A.attest(receipt,report,self.proposal,self.policy,self.key,executable=OPENSSL)
        self.assertTrue(A.verify(envelope,self.policy,executable=OPENSSL));self.assertNotIn(self.key.decode(),json.dumps(envelope));self.assertFalse(report['production_authorized'])
    def test_wrong_request_peer_refused_before_cache(self):
        policy={**self.export_policy,'requester_uid':os.getuid()+1};self.assertEqual(self.export(policy,raw=(self.proposal+'\n').encode())['code'],'COLLECTOR_EXPORT_REFUSED')
    def test_arbitrary_path_and_extra_request_refused(self):
        for raw in [b'../../private\n',(self.proposal+'\nX').encode(),(self.proposal.upper()+'\n').encode()]:
            with self.subTest(raw=raw):self.assertEqual(self.export(raw=raw)['code'],'COLLECTOR_EXPORT_REFUSED')
    def test_shared_lock_conflict_refused(self):
        fd=os.open(self.cache/'.collection.lock',os.O_RDWR);fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:self.assertEqual(self.export(raw=(self.proposal+'\n').encode())['code'],'COLLECTOR_EXPORT_REFUSED')
        finally:os.close(fd)
    def test_artifact_tamper_and_symlink_refused(self):
        p=self.cache/self.proposal/'server';p.chmod(0o600);p.write_bytes(b'X'*len(self.bodies[0]));p.chmod(0o400)
        self.assertEqual(self.export(raw=(self.proposal+'\n').encode())['code'],'COLLECTOR_EXPORT_REFUSED')
        p.unlink();p.symlink_to('frontend.tar');self.assertEqual(self.export(raw=(self.proposal+'\n').encode())['code'],'COLLECTOR_EXPORT_REFUSED')
    def test_unsealed_descriptor_refused(self):
        fd=os.memfd_create('invented',os.MFD_ALLOW_SEALING);os.write(fd,b'invented')
        try:
            with self.assertRaisesRegex(C.Refused,'UNSEALED'):C.sealed_bytes(fd,100)
        finally:os.close(fd)
    def test_real_sender_uid_not_json_claim(self):
        left,right=self.pair();left.setsockopt(socket.SOL_SOCKET,socket.SO_PASSCRED,1)
        try:
            right.sendall(b'invented')
            with self.assertRaisesRegex(C.Refused,'SENDER_UID'):C.packet(left,100,end=time.monotonic()+1,expected_uid=os.getuid()+1)
        finally:left.close();right.close()
    def test_extra_descriptor_closed_on_refusal(self):
        before=len(os.listdir('/proc/self/fd'));left,right=self.pair();fd=C.memfd(b'invented')
        try:
            C.send_packet(right,b'invented',[fd],end=time.monotonic()+1)
            with self.assertRaisesRegex(C.Refused,'DESCRIPTORS'):C.packet(left,100,end=time.monotonic()+1)
        finally:left.close();right.close();os.close(fd)
        self.assertEqual(len(os.listdir('/proc/self/fd')),before)
    def test_unknown_ancillary_before_rights_does_not_leak_descriptor(self):
        before=len(os.listdir('/proc/self/fd'));left,right=self.pair();fd=C.memfd(b'invented')
        left.setsockopt(socket.SOL_SOCKET,socket.SO_PASSCRED,1)
        try:
            C.send_packet(right,b'invented',[fd],end=time.monotonic()+1)
            # Credentials are deliberately not admitted by this call. The
            # kernel may place them before an already allocated SCM_RIGHTS fd.
            with self.assertRaises(C.Refused):C.packet(left,100,end=time.monotonic()+1)
        finally:left.close();right.close();os.close(fd)
        self.assertEqual(len(os.listdir('/proc/self/fd')),before)
    def test_required_steps_sources_policy_and_false_claims_preserved(self):
        changes=[('steps',[]),('sources',[]),('policy_sha256','0'*64),('rules_revision','0'*40),('production_authorized',True),('independent_adoption_established',True),('not_established',[])]
        for field,value in changes:
            report=copy.deepcopy(self.report);report[field]=value
            with self.subTest(field=field),self.assertRaises(C.Refused):A.attest(self.receipt,report,self.proposal,self.policy,self.key,executable=OPENSSL)
    def test_expired_unadopted_and_identity_collision_refused(self):
        for value in [{**self.policy,'expires_at':int(time.time())-1},{**self.policy,'accepted_proposals':['0'*64]},{**self.policy,'signer_uid':os.getuid()}]:
            with self.assertRaises(C.Refused):A.attest(self.receipt,self.report,self.proposal,value,self.key,executable=OPENSSL)
    def test_signature_modified_artifact_wrong_key_wrong_domain_refused(self):
        envelope=A.attest(self.receipt,self.report,self.proposal,self.policy,self.key,executable=OPENSSL)
        forged=copy.deepcopy(envelope);forged['payload']['artifacts'][0]['sha256']='0'*64
        with self.assertRaises(C.Refused):A.verify(forged,self.policy,executable=OPENSSL)
        other=subprocess.check_output([OPENSSL,'genpkey','-algorithm','ED25519'],stderr=subprocess.DEVNULL)
        with self.assertRaises(C.Refused):A.attest(self.receipt,self.report,self.proposal,self.policy,other,executable=OPENSSL)
        forged=copy.deepcopy(envelope);forged['payload']['scope']='invented-other-domain'
        with self.assertRaises(C.Refused):A.verify(forged,self.policy,executable=OPENSSL)
    def test_legacy_cache_cannot_be_exported_or_signed(self):
        legacy=K.legacy_response(self.receipt)
        p=self.cache/self.proposal/'receipt.json';p.chmod(0o600);p.write_bytes(C.canonical(legacy));p.chmod(0o400)
        self.assertEqual(self.export(raw=(self.proposal+'\n').encode())['code'],'COLLECTOR_EXPORT_REFUSED')
        with self.assertRaises(C.Refused):A.attest(legacy,self.report,self.proposal,self.policy,self.key,executable=OPENSSL)
    def test_producer_binding_checks_actual_recipes_policy_and_closure(self):
        configuration={'rules_revision':self.rules,'validator_store':self.policy['verifier']}
        raw=C.canonical(configuration);closure=(self.policy['verifier']+'\n').encode()
        binding={**self.binding,'worker_policy_sha256':C.sha(raw),'closure_sha256':C.sha(closure)}
        P.verify_configuration(binding,configuration,raw,closure)
        for field in ['verifier','worker_policy_sha256','closure_sha256','producer_recipe_sha256','worker_core_sha256','contract_sha256']:
            wrong=copy.deepcopy(binding);wrong[field]=('/nix/store/'+'1'*32+'-wrong') if field=='verifier' else '0'*64
            with self.subTest(field=field),self.assertRaises(C.Refused):P.verify_configuration(wrong,configuration,raw,closure)
    def test_bound_collection_then_cache_and_legacy_client_projection(self):
        K.EXPECTED_BINDING=self.binding
        directory=self.root/'fresh';directory.mkdir(mode=0o700);fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY)
        left,right=socket.socketpair();wire=C.canonical(self.receipt)+b'\n'+b''.join(self.bodies)
        def send():
            with right:right.sendall(wire)
        thread=threading.Thread(target=send);thread.start()
        try:observed=K.receive(left,fd,self.proposal,self.rules,deadline=time.monotonic()+1)
        finally:left.close();thread.join(2);os.close(fd)
        self.assertEqual(observed,self.receipt)
        projection=K.legacy_response(observed)
        self.assertEqual(S.validate_receipt(projection,self.proposal,self.rules),projection)
        self.assertEqual(C.parse((directory/'receipt.json').read_bytes())['producer'],self.binding)
        wrong=copy.deepcopy(self.receipt);wrong['producer']['verifier']='/nix/store/'+'1'*32+'-wrong'
        with self.assertRaises(C.Refused):K.validate_receipt(wrong,self.proposal,self.rules)
    def test_strict_json_and_no_dynamic_request_policy(self):
        for raw in [b'{"x":1,"x":2}',b'{"x":1.0}',b'{"x":NaN}',b'{}\n{}']:
            with self.assertRaises(C.Refused):C.parse(raw)
        value={**self.policy,'client_policy':True}
        with self.assertRaises(C.Refused):C.policy(value)
    def client_policy(self):
        return {**self.policy,'signer_uid':os.getuid(),'collector_uid':os.getuid()+1,'requester_uid':os.getuid()+2}
    def client_exchange(self,value,envelope,*,extra=None,descriptors=()):
        left,right=self.pair();errors=[]
        def reply():
            try:
                with right:
                    self.assertEqual(C.request(right,end=time.monotonic()+2),self.proposal)
                    if extra is None:C.send_packet(right,C.canonical(envelope),list(descriptors),end=time.monotonic()+2)
                    else:
                        right.sendall(C.canonical(envelope));right.sendall(extra);right.shutdown(socket.SHUT_WR)
            except BaseException as error:errors.append(error)
        thread=threading.Thread(target=reply);thread.start()
        try:
            with left:return V.receive(left,self.proposal,value,end=time.monotonic()+2,executable=OPENSSL)
        finally:
            thread.join(3);self.assertFalse(thread.is_alive());self.assertEqual(errors,[])
    def test_client_verifies_actual_sender_signature_policy_and_requested_digest(self):
        value=self.client_policy();envelope=A.attest(self.receipt,self.report,self.proposal,value,self.key,executable=OPENSSL)
        self.assertEqual(self.client_exchange(value,envelope),envelope)
    def test_client_refuses_signature_tamper_extra_packet_and_descriptor(self):
        value=self.client_policy();envelope=A.attest(self.receipt,self.report,self.proposal,value,self.key,executable=OPENSSL)
        wrong=copy.deepcopy(envelope);wrong['signature']=base64.b64encode(b'X'*64).decode()
        with self.assertRaises(C.Refused):self.client_exchange(value,wrong)
        with self.assertRaises(C.Refused):self.client_exchange(value,envelope,extra=b'X')
        descriptor=C.memfd(b'invented')
        try:
            with self.assertRaises(C.Refused):self.client_exchange(value,envelope,descriptors=[descriptor])
        finally:os.close(descriptor)
    def test_client_refuses_valid_signature_for_other_adopted_proposal(self):
        value={**self.client_policy(),'accepted_proposals':['a'*64,'c'*64]}
        report={**self.report,'proposal_sha256':'c'*64};bodies=self.bodies[:2]+[C.canonical(report)]
        receipt={**self.receipt,'proposal_sha256':'c'*64,'artifacts':[{'name':name,'bytes':len(raw),'sha256':C.sha(raw)} for (name,_),raw in zip(C.ARTIFACTS,bodies)]}
        envelope=A.attest(receipt,report,'c'*64,value,self.key,executable=OPENSSL)
        self.assertTrue(A.verify(envelope,value,executable=OPENSSL))
        with self.assertRaisesRegex(C.Refused,'REQUEST_BINDING_REFUSED'):self.client_exchange(value,envelope)
    def test_client_deadline_covers_silent_sender_and_crypto(self):
        left,right=self.pair();value=self.client_policy();start=time.monotonic()
        try:
            with self.assertRaises((C.Refused,TimeoutError)):V.receive(left,self.proposal,value,end=start+0.05,executable=OPENSSL)
        finally:left.close();right.close()
        self.assertLess(time.monotonic()-start,0.5)
        envelope=A.attest(self.receipt,self.report,self.proposal,value,self.key,executable=OPENSSL)
        with self.assertRaisesRegex(C.Refused,'AUTHORITY_TIMEOUT'):A.verify(envelope,value,executable=OPENSSL,end=time.monotonic()-1)

if __name__=='__main__':unittest.main(verbosity=2)
