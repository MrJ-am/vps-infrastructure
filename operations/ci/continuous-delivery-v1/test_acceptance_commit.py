import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import test_admission_orchestrator
import acceptance_commit as K

class Commit(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.state=Path(self.tmp.name)/'ledger';self.state.mkdir(mode=0o700)
        self.jobs=Path(self.tmp.name)/'jobs';self.jobs.mkdir(mode=0o700)
        self.a=self.job(1);self.b=self.job(2)
    def job(self,n):
        j={'schema_version':1,'id':format(n,'064x'),'phase':'validated','capture':{'proposal_sha256':format(n+10,'064x')},'ready':{'base_sha256':'a'*64}}
        p=self.jobs/j['id'];p.mkdir(mode=0o700);K.O.save(p/'state.json',j);return j
    def acquire(self,j):K.acquire(self.state,self.jobs,j)
    def test_lost_response_retains_owner(self):
        self.acquire(self.a);self.acquire(self.a)
        with self.assertRaisesRegex(Exception,'ACCEPTANCE_PREVIOUS_DELIVERY_PENDING'):self.acquire(self.b)
        self.assertEqual(json.loads((self.state/'commit.json').read_bytes()),K.identity(self.a))
    def test_completed_deployment_allows_next_owner(self):
        self.acquire(self.a);self.a.update(phase='deployed',delivery={'proposal_sha256':self.a['capture']['proposal_sha256'],'plan_sha256':'f'*64})
        K.O.save(self.jobs/self.a['id']/'state.json',self.a);self.acquire(self.b)
        self.assertEqual(json.loads((self.state/'commit.json').read_bytes()),K.identity(self.b))
    def test_failure_or_obsolescence_never_erases_ambiguous_merge(self):
        self.acquire(self.a)
        for phase in ('obsolete','failed'):
            self.a['phase']=phase;K.O.save(self.jobs/self.a['id']/'state.json',self.a)
            with self.assertRaisesRegex(Exception,'ACCEPTANCE_PREVIOUS_DELIVERY_PENDING'):self.acquire(self.b)
    def test_deployed_without_receipt_refused(self):
        self.acquire(self.a);self.a['phase']='deployed';K.O.save(self.jobs/self.a['id']/'state.json',self.a)
        with self.assertRaisesRegex(Exception,'ACCEPTANCE_PREVIOUS_DELIVERY_PENDING'):self.acquire(self.b)
    def test_changed_identity_refused(self):
        self.acquire(self.a);self.a['capture']['proposal_sha256']='e'*64;K.O.save(self.jobs/self.a['id']/'state.json',self.a)
        with self.assertRaisesRegex(Exception,'ACCEPTANCE_COMMIT_OWNER_CHANGED'):self.acquire(self.b)
    def test_malformed_record_not_overwritten(self):
        K.O.save(self.state/'commit.json',{'schema_version':1})
        with self.assertRaisesRegex(Exception,'ACCEPTANCE_COMMIT_RECORD_REFUSED'):self.acquire(self.b)
    def returned_fixture(self):
        root=Path(self.tmp.name)/'promotion';root.mkdir(mode=0o700)
        p=patch.object(K,'PROMOTION',root);p.start();self.addCleanup(p.stop)
        plan={'schema_version':1,'profile':'vise-v1','job':self.a['id'],
            'proposal_sha256':self.a['capture']['proposal_sha256'],
            'old':'/nix/store/'+'a'*32+'-nixos-system-old'}
        key=K.O.sha(K.O.encode(plan))
        K.O.save(root/'plan.json',plan)
        self.a['delivery_return']={'plan_sha256':key,'generation':plan['old']}
        K.O.save(self.jobs/self.a['id']/'state.json',self.a)
        K.O.save(root/(key+'.json'),{'schema_version':1,'plan_sha256':key,'phase':'failed'})
        return root,key
    def test_confirmed_vise_return_releases_both_acceptance_and_staging(self):
        import staging_lease as L
        self.acquire(self.a);self.returned_fixture()
        self.assertIsNone(L.pending_commit(self.state,self.jobs))
        self.acquire(self.b)
        self.assertEqual(json.loads((self.state/'commit.json').read_bytes()),K.identity(self.b))
    def test_recovery_intent_and_unbound_return_do_not_release_owner(self):
        import staging_lease as L
        self.acquire(self.a);root,key=self.returned_fixture()
        for phase in ('recovering','prepared','complete'):
            K.O.save(root/(key+'.json'),{'schema_version':1,'plan_sha256':key,'phase':phase})
            self.assertEqual(L.pending_commit(self.state,self.jobs),K.identity(self.a))
            with self.assertRaisesRegex(Exception,'ACCEPTANCE_PREVIOUS_DELIVERY_PENDING'):self.acquire(self.b)
        K.O.save(root/(key+'.json'),{'schema_version':1,'plan_sha256':key,'phase':'failed'})
        self.a['delivery_return']['generation']='wrong'
        K.O.save(self.jobs/self.a['id']/'state.json',self.a)
        with self.assertRaisesRegex(Exception,'ACCEPTANCE_PREVIOUS_DELIVERY_PENDING'):self.acquire(self.b)

if __name__=='__main__':unittest.main()
