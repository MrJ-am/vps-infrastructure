import copy,unittest
import test_preparation_plan as F
import accepted_plan as P

class Accepted(unittest.TestCase):
    def setUp(self):
        self.f=F.Plan();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.plan=self.f.create();self.job=self.f.job
        self.job['capture']['proposal']['head']='a'*40
        for k in ('old','new'):self.plan[k]='/nix/store/'+'a'*32+'-nixos-system-'+k
        self.plan['environment']['system']=self.plan['old']
        self.owner=P.K.identity(self.job)
        row={'repository':'etp-vie-affective','head':'a'*40,'number':3,'proposal_sha256':'c'*64}
        self.ledger={'schema_version':1,'job':self.job['id'],'proposal_sha256':'c'*64,
            'receipts':{'mirror':dict(row),'review':{**row,'review_id':9},
                'merge':{**row,'review_id':9,'protected_fast_forward':True,'merger':'mrjam-release-merge'},
                'sync':{'repository':'etp-vie-affective','head':'a'*40,'canonical_forgejo_main':True,
                    'github_main_synchronized':True,'token_revoked':True}},
            'inflight':None,'next_attempt':0,'attempts':0,'code':None}
    def compose(self):return P.compose(self.plan,self.owner,self.job,self.ledger)
    def test_transition_binds_reserved_plan_and_all_receipts(self):
        result=self.compose();self.assertEqual(result['profile'],'vise-v1')
        self.assertEqual(result['accepted_plan_sha256'],P.O.sha(P.O.encode(self.plan)))
        self.assertEqual(result['acceptance_sha256'],P.O.sha(P.O.encode(self.ledger)))
        self.assertEqual(result['old'],self.plan['old']);self.assertNotIn('slot',result)
    def test_missing_sync_refused(self):
        self.ledger['receipts'].pop('sync')
        with self.assertRaisesRegex(Exception,'ENQUEUE_ACCEPTANCE_INCOMPLETE'):self.compose()
    def test_other_acceptance_owner_refused(self):
        self.owner['job']='f'*64
        with self.assertRaisesRegex(Exception,'VISE_ACCEPTED_OWNER_CHANGED'):self.compose()
    def test_changed_head_in_each_receipt_refused(self):
        for stage in self.ledger['receipts']:
            with self.subTest(stage=stage):
                self.ledger['receipts'][stage]['head']='b'*40
                with self.assertRaisesRegex(Exception,'ENQUEUE_SOURCE_RECEIPT_CHANGED'):self.compose()
                self.ledger['receipts'][stage]['head']='a'*40
    def test_missing_sync_guarantees_refused(self):
        for key in ('canonical_forgejo_main','github_main_synchronized','token_revoked'):
            with self.subTest(key=key):
                self.ledger['receipts']['sync'][key]=False
                with self.assertRaisesRegex(Exception,'ENQUEUE_SYNC_REFUSED'):self.compose()
                self.ledger['receipts']['sync'][key]=True
    def test_wrong_merge_identity_or_review_refused(self):
        for key,bad in [('merger','other'),('review_id',10),('protected_fast_forward',False)]:
            with self.subTest(key=key):
                old=self.ledger['receipts']['merge'][key];self.ledger['receipts']['merge'][key]=bad
                with self.assertRaisesRegex(Exception,'ENQUEUE_MERGE_REFUSED'):self.compose()
                self.ledger['receipts']['merge'][key]=old
    def test_different_initial_generation_refused(self):
        self.plan['environment']['system']=self.plan['new']
        with self.assertRaisesRegex(Exception,'VISE_ACCEPTED_PREPARATION_REFUSED'):self.compose()
    def test_two_missing_review_ids_do_not_count_as_matching_review(self):
        self.ledger['receipts']['review'].pop('review_id');self.ledger['receipts']['merge'].pop('review_id')
        with self.assertRaisesRegex(Exception,'ENQUEUE_MERGE_REFUSED'):self.compose()
    def test_candidate_cannot_add_an_activation_command(self):
        self.plan['command']='synthetic'
        with self.assertRaises(Exception):self.compose()
    def test_load_reads_the_reserved_plan_and_durable_ledger(self):
        state=self.f.work/'acceptance';jobs=self.f.work/'jobs'
        for path in (state,jobs,state/'vise-plans',state/self.job['id'],jobs/self.job['id']):path.mkdir(mode=0o700)
        self.job['schema_version']=1
        P.O.save(jobs/self.job['id']/'state.json',self.job)
        P.O.save(state/'commit.json',self.owner)
        P.O.save(state/'vise-plans'/(self.job['id']+'.json'),self.plan)
        P.O.save(state/self.job['id']/'state.json',self.ledger)
        self.assertEqual(P.load(state,jobs,self.job['id']),self.compose())
        self.ledger['receipts']['sync']['token_revoked']=False
        P.O.save(state/self.job['id']/'state.json',self.ledger)
        with self.assertRaisesRegex(Exception,'ENQUEUE_SYNC_REFUSED'):P.load(state,jobs,self.job['id'])
    def test_job_path_traversal_refused(self):
        with self.assertRaisesRegex(Exception,'VISE_ACCEPTED_JOB_PATH_REFUSED'):
            P.load(self.f.work,self.f.work,'../other')

if __name__=='__main__':unittest.main()
