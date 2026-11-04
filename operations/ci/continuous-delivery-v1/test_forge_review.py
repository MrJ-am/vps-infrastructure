import copy,unittest
from unittest.mock import patch
import test_validation_feedback as F
import test_forge_proposal as M
import forge_review as R

class Review(unittest.TestCase):
    def setUp(self):
        self.f=F.Feedback();self.f.setUp();self.m=M.Mirror();self.m.setUp();self.m.mirror()
        self.rows=[];self.posts=[];self.verified=True;self.lost=False
    def request(self,method,path,body=None):
        if method=='GET' and path=='/pulls/2':return self.m.pr
        if method=='GET' and path.startswith('/pulls/2/reviews?'):return self.rows
        if method=='POST':
            self.posts.append(path)
            if path.endswith('/reviews'):
                row={'id':10,'user':{'login':R.R.ROLES['review']},'state':'APPROVED',
                    'commit_id':body['commit_id'],'body':body['body'],'official':True,'stale':False,'dismissed':False}
                self.rows.append(row)
                if self.lost:raise TimeoutError('synthetic lost response')
                return row
            return {'id':11,**body}
        return self.m.request(method,path,body)
    def approve(self):
        return R.approve(self.f.proposal,2,self.f.run,self.f.policy,self.f.envelope,self.request,
            verify=lambda *args:self.verified)
    def test_signed_result_produces_technical_review_never_merge(self):
        result=self.approve();self.assertEqual(result['reviewer'],'mrjam-validation-review')
        self.assertFalse(result['human_review']);self.assertFalse(result['merged'])
        self.assertEqual(self.m.main,'a'*40);self.assertEqual(len(self.posts),2)
    def test_invalid_signature_has_no_effect(self):
        self.verified=False
        with self.assertRaisesRegex(Exception,'REVIEW_SIGNATURE_REFUSED'):self.approve()
        self.assertEqual(self.posts,[])
    def test_wrong_run_or_source_has_no_effect(self):
        for key,value in [('status','failure'),('proposal_sha256','e'*64),('rules_revision','e'*40)]:
            original=copy.deepcopy(self.f.run);self.f.run[key]=value
            with self.assertRaisesRegex(Exception,'REVIEW_RUN_REFUSED'):self.approve()
            self.f.run=original
        self.f.policy['sources'][0]['revision']='f'*40
        with self.assertRaisesRegex(Exception,'REVIEW_SOURCE_REFUSED'):self.approve()
        self.assertEqual(self.posts,[])
    def test_changed_main_or_head_has_no_effect(self):
        self.m.main='e'*40
        with self.assertRaisesRegex(Exception,'REVIEW_BASE_MOVED'):self.approve()
        self.m.main='a'*40;self.m.pr['head']['sha']='f'*40
        with self.assertRaisesRegex(Exception,'REVIEW_PROPOSAL_CHANGED'):self.approve()
        self.assertEqual(self.posts,[])
    def test_lost_approval_response_reconciles_without_duplicate(self):
        self.lost=True
        with self.assertRaises(TimeoutError):self.approve()
        self.lost=False;self.approve();self.assertEqual(len(self.posts),2)
    def test_official_rejection_is_respected(self):
        self.rows=[{'state':'REQUEST_CHANGES','official':True,'dismissed':False}]
        with self.assertRaisesRegex(Exception,'REVIEW_CHANGES_REQUESTED'):self.approve()
        self.assertEqual(self.posts,[])
    def test_stale_or_dismissed_review_is_not_reused(self):
        self.approve();self.rows[0]['stale']=True
        self.approve();self.assertEqual(len(self.posts),4)
    def test_api_cannot_merge_change_protection_or_write_source(self):
        api=R.API(self.f.proposal,2,'synthetic','synthetic')
        with patch.object(R.http.client,'HTTPConnection') as connection:
            for method,path in [('POST','/pulls/2/merge'),('PATCH','/branch_protections/main'),('POST','/contents/a')]:
                with self.assertRaisesRegex(Exception,'REVIEW_API_ROUTE_REFUSED'):api(method,path,{})
            connection.assert_not_called()

if __name__=='__main__':unittest.main()
