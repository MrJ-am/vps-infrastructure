import unittest
from unittest.mock import patch
import test_validation_feedback as F
import github_accepted_main as S

class Sync(unittest.TestCase):
    def setUp(self):
        self.f=F.Feedback();self.f.setUp();self.main='a'*40;self.writes=0;self.revoked=False;self.lost=False
        self.accepted={'repository':'mrjam-plateforme','head':'b'*40,'protected_fast_forward':True,'merger':'mrjam-release-merge'}
    def request(self,path,token,method='GET',body=None):
        if path.endswith('/access_tokens'):return 201,{'token':'synthetic','permissions':S.PERMISSIONS}
        if method=='DELETE':self.revoked=True;return 204,None
        if '/pulls/' in path:return self.f.request(path,token,method,body)
        if '/git/' in path:
            if method=='PATCH':
                self.assertEqual(body,{'sha':'b'*40,'force':False});self.main=body['sha'];self.writes+=1
                if self.lost:raise TimeoutError('synthetic lost response')
            return 200,{'ref':'refs/heads/main','object':{'type':'commit','sha':self.main}}
        return 200,{'id':1437120781,'full_name':'MrJ-am/mrjam-plateforme','private':True,'default_branch':'main'}
    def sync(self):
        with patch.object(S.P.A,'jwt',return_value='synthetic'):
            return S.sync(self.f.proposal,self.accepted,self.f.credentials,request=self.request)
    def test_exact_canonical_head_synced_token_revoked(self):
        result=self.sync();self.assertTrue(result['token_revoked']);self.assertEqual(self.writes,1)
    def test_changed_base_not_overwritten(self):
        self.main='f'*40
        with self.assertRaisesRegex(Exception,'SYNC_BASE_MOVED'):self.sync()
        self.assertEqual(self.writes,0);self.assertTrue(self.revoked)
    def test_unaccepted_source_never_synced(self):
        self.accepted['protected_fast_forward']=False
        with self.assertRaisesRegex(Exception,'SYNC_CANONICAL_ACCEPTANCE_REFUSED'):self.sync()
        self.assertEqual(self.writes,0)
    def test_lost_response_reconciles_without_another_write(self):
        self.lost=True
        with self.assertRaises(TimeoutError):self.sync()
        self.assertTrue(self.revoked);self.lost=False
        self.assertTrue(self.sync()['recovered_existing']);self.assertEqual(self.writes,1)
    def test_changed_proposal_not_synced(self):
        self.f.moved=True
        with self.assertRaisesRegex(Exception,'SYNC_PROPOSAL_CHANGED'):self.sync()
        self.assertEqual(self.writes,0);self.assertTrue(self.revoked)

if __name__=='__main__':unittest.main()
