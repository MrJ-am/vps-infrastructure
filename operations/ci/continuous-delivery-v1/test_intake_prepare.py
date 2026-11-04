"""Local queue -> real Git objects -> live source gate -> durable result.

Network transport is replaced with a local reader; no remote branch, workflow,
admission or application is changed by these tests.
"""
import fcntl,json,unittest
from unittest.mock import patch
import test_intake_queue as T
import test_proposal_prepare as B
import intake_prepare as W

class Interrupted(BaseException):pass

class IntakePreparation(unittest.TestCase):
    def setUp(self):
        self.fixture=B.Preparation('runTest');self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root=self.fixture.root
        self.state=self.root/'state';self.state.mkdir(mode=0o700)
        self.spool=self.root/'spool';self.spool.mkdir(mode=0o700)
        self.scratch=self.root/'scratch';self.scratch.mkdir(mode=0o700)
        self.q=T.Q.Queue(self.state);self.addCleanup(self.q.close)
        self.now=10;self.fetches=0
        self.proposal=T.proposal(head=self.fixture.commit());self.proposal['base']=B.HEAD
    def receive(self,directory,git,proposal,credentials):
        self.fetches+=1
        self.assertFalse(list(directory.iterdir()))
        self.assertEqual(proposal,self.proposal)
        return W.Q.S.NativeObjects(self.fixture.repo,B.GIT)
    def run_once(self,**kwargs):
        return W.once(self.q,self.spool,self.scratch,B.BASE,B.DIGEST,B.POLICY,
            git=B.GIT,credentials=None,validator_policy=B.P,gate=B.G,gate_path=B.GATE,
            clock=lambda:self.now,receive=kwargs.get('receive',self.receive))
    def selected_once(self,provider):
        # Invalid fallback inputs prove the installed provider supplies the
        # actual source/policy binding, rather than merely being notified.
        return W.once(self.q,self.spool,self.scratch,None,None,None,
            git=B.GIT,credentials=None,validator_policy=None,gate=B.G,gate_path=B.GATE,
            clock=lambda:self.now,receive=self.receive,select_base=provider)
    def test_selected_adoption_is_bound_into_the_real_receipt(self):
        seen=[]
        def provider(proposal):
            seen.append(proposal)
            return B.BASE,B.DIGEST,B.POLICY,B.P
        self.q.observe([self.proposal],1)
        result=self.selected_once(provider)
        self.assertEqual(result['code'],'PREPARATION_READY')
        receipt=json.loads((self.spool/result['result']/'receipt.json').read_bytes())
        self.assertEqual(receipt['base_sha256'],B.DIGEST)
        self.assertEqual(seen,[self.proposal])
        self.assertEqual(self.selected_once(provider)['code'],'PREPARATION_IDLE')
        self.assertEqual(len(seen),1)
    def test_unavailable_selected_profile_cannot_block_another_repository(self):
        import delivery_profiles as Profiles
        def provider(proposal):
            if Profiles.selected(proposal)=='vise':
                raise W.Q.S.Refused('PROJECT_RECIPE_UNAVAILABLE')
            return B.BASE,B.DIGEST,B.POLICY,B.P
        vise=T.proposal(repository='etp-vie-affective')
        self.q.observe([vise],1)
        self.assertEqual(self.selected_once(provider)['code'],'PROJECT_RECIPE_UNAVAILABLE')
        self.assertEqual(self.fetches,0)
        self.q.observe([vise,self.proposal],11);self.now=12
        self.assertEqual(self.selected_once(provider)['code'],'PREPARATION_READY')
    def test_exact_queue_to_real_source_and_receipt(self):
        self.q.observe([self.proposal],1);result=self.run_once()
        self.assertEqual(result['code'],'PREPARATION_READY');self.assertEqual(self.fetches,1)
        self.assertFalse(result['deployment_authorized']);self.assertFalse(result['admission_performed'])
        target=self.spool/result['result'];receipt=json.loads((target/'receipt.json').read_bytes())
        self.assertEqual(receipt['proposal'],self.proposal)
        self.assertEqual(W.C.sha((target/'receipt.json').read_bytes()),self.q.ready()[0]['receipt'])
        policy=json.loads((target/'policy.json').read_bytes())
        source=next(s for s in policy['sources'] if s['id']=='platform')
        self.assertEqual(source['revision'],self.proposal['head'])
        # Run the separate consumer's policy verifier with independently
        # obtained local Git metadata, not the receipt's claimed tree.
        tree=self.fixture.git('rev-parse',self.proposal['head']+'^{tree}')
        B.V.verify(target/'source',B.POLICY,policy,{'platform':{
            'repository':'MrJ-am/mrjam-plateforme','revision':self.proposal['head'],'tree_sha':tree}},
            receipt['proposal_sha256'],validator_policy=B.P,gate_path=B.GATE)
        self.assertEqual(self.run_once()['code'],'PREPARATION_IDLE')
    def test_crash_after_publication_recovers_without_refetch(self):
        self.q.observe([self.proposal],1)
        with patch.object(self.q,'finish',side_effect=Interrupted):
            with self.assertRaises(Interrupted):self.run_once()
        self.assertEqual(len(list(self.spool.glob('[0-9a-f]'*64))),1)
        self.now=1000;result=self.run_once()
        self.assertEqual(result['code'],'PREPARATION_READY');self.assertEqual(self.fetches,1)
        self.assertEqual(self.q.db.execute('SELECT attempts FROM jobs').fetchone()[0],2)
    def test_recovery_rechecks_source_bytes(self):
        self.q.observe([self.proposal],1)
        with patch.object(self.q,'finish',side_effect=Interrupted):
            with self.assertRaises(Interrupted):self.run_once()
        target=next(p for p in self.spool.iterdir() if p.is_dir())
        (target/'source/sources/platform/Cargo.toml').write_text('invented corruption')
        self.now=1000;self.assertNotEqual(self.run_once()['code'],'PREPARATION_READY')
        self.assertEqual(self.q.ready(),[]);self.assertEqual(self.fetches,1)
    def test_expired_worker_cannot_complete_but_next_claim_recovers(self):
        self.q.observe([self.proposal],1)
        def slow(*args):
            reader=self.receive(*args);self.now=1000;return reader
        self.assertEqual(self.run_once(receive=slow)['code'],'QUEUE_STALE_LEASE')
        self.assertEqual(self.q.ready(),[])
        self.assertEqual(self.run_once()['code'],'PREPARATION_READY');self.assertEqual(self.fetches,1)
    def test_unavailable_vise_recipe_does_not_block_platform(self):
        vise=T.proposal(repository='etp-vie-affective')
        self.q.observe([vise],1)
        self.assertEqual(self.run_once()['code'],'PROJECT_RECIPE_UNAVAILABLE')
        self.q.observe([vise,self.proposal],11);self.now=12
        self.assertEqual(self.run_once()['code'],'PREPARATION_READY')
    def test_only_one_worker_claims(self):
        self.q.observe([self.proposal],1)
        with (self.spool/'prepare.lock').open('w') as stream:
            (self.spool/'prepare.lock').chmod(0o600);fcntl.flock(stream,fcntl.LOCK_EX)
            self.assertEqual(self.run_once()['code'],'PREPARATION_BUSY')
        self.assertEqual(self.run_once()['code'],'PREPARATION_READY')
    def test_unpublished_staging_is_recovered_but_results_are_retained(self):
        staging=self.spool/'.incomplete';staging.mkdir(mode=0o700)
        (staging/'partial').write_text('invented partial output')
        self.assertEqual(self.run_once()['code'],'PREPARATION_IDLE')
        self.assertFalse(staging.exists())
        self.q.observe([self.proposal],1);result=self.run_once()
        self.q.acknowledge(result['key'],result['receipt'],11)
        self.assertEqual(self.run_once()['code'],'PREPARATION_IDLE')
        self.assertTrue((self.spool/result['result']).is_dir())
    def test_capacity_refusal_before_network_and_no_result_removed(self):
        for n in range(W.MAX_RESULTS):(self.spool/format(n,'064x')).mkdir(mode=0o700)
        self.q.observe([self.proposal],1)
        self.assertEqual(self.run_once()['code'],'PREPARATION_CAPACITY_REACHED')
        self.assertEqual(self.fetches,0);self.assertEqual(len(list(self.spool.iterdir())),17)
    def test_reprepare_requires_current_receipt(self):
        self.q.observe([self.proposal],1);result=self.run_once()
        with self.assertRaisesRegex(W.Q.S.Refused,'QUEUE_REPREPARE_REFUSED'):
            self.q.reprepare(result['key'],'0'*64,11)
        self.q.reprepare(result['key'],result['receipt'],11)
        self.now=12;self.assertEqual(self.run_once()['code'],'PREPARATION_READY')
        self.assertEqual(self.fetches,1)
        self.q.acknowledge(result['key'],result['receipt'],13)
        with self.assertRaisesRegex(W.Q.S.Refused,'QUEUE_REPREPARE_REFUSED'):
            self.q.reprepare(result['key'],result['receipt'],14)
    def test_no_raw_exception_text_is_exported(self):
        self.q.observe([self.proposal],1)
        def failing(*args):raise RuntimeError('invented credential must not escape')
        result=self.run_once(receive=failing)
        self.assertEqual(result['code'],'SOURCE_PREPARATION_REFUSED')
        self.assertNotIn('credential',json.dumps(result))

if __name__=='__main__':unittest.main()
