import unittest
from unittest.mock import patch
import test_forge_review as T
import forge_merge as M

class Merge(unittest.TestCase):
    def setUp(self):
        self.t=T.Review();self.t.setUp();self.receipt=self.t.approve()
        self.t.m.pr['mergeable']=True;self.merges=0;self.lost=False
    def request(self,method,path,body=None):
        if method=='POST' and path=='/pulls/2/merge':
            self.assertFalse(body['force_merge']);self.assertEqual(body['Do'],'fast-forward-only')
            self.t.m.pr.update(merged=True,state='closed',merge_commit_sha='b'*40,merged_by={'login':M.R.ROLES['merge']})
            self.t.m.main='b'*40;self.merges+=1
            if self.lost:raise TimeoutError('synthetic lost response')
            return None
        return self.t.request(method,path,body)
    def merge(self):
        f=self.t.f
        return M.merge(f.proposal,2,f.run,f.policy,f.envelope,self.receipt,self.request,verify=lambda *args:self.t.verified)
    def test_exact_protected_fast_forward(self):
        result=self.merge();self.assertTrue(result['protected_fast_forward']);self.assertFalse(result['deployed'])
        self.assertEqual(self.merges,1)
    def test_lost_response_is_reconciled(self):
        self.lost=True
        with self.assertRaises(TimeoutError):self.merge()
        self.lost=False;self.assertTrue(self.merge()['recovered_existing']);self.assertEqual(self.merges,1)
    def test_signature_required_even_if_green_and_reviewed(self):
        self.t.verified=False
        with self.assertRaisesRegex(Exception,'MERGE_SIGNATURE_REFUSED'):self.merge()
        self.assertEqual(self.merges,0)
    def test_stale_review_rejected(self):
        self.t.rows[0]['stale']=True
        with self.assertRaisesRegex(Exception,'MERGE_REVIEW_REFUSED'):self.merge()
        self.assertEqual(self.merges,0)
    def test_base_changed_rejected(self):
        self.t.m.main='f'*40
        with self.assertRaisesRegex(Exception,'MERGE_BASE_MOVED'):self.merge()
        self.assertEqual(self.merges,0)
    def test_rejected_review_not_overridden(self):
        self.t.rows.append({'state':'REQUEST_CHANGES','official':True,'dismissed':False})
        with self.assertRaisesRegex(Exception,'MERGE_CHANGES_REQUESTED'):self.merge()
        self.assertEqual(self.merges,0)
    def test_other_merger_cannot_supply_recovery(self):
        self.merge();self.t.m.pr['merged_by']['login']='another'
        with self.assertRaisesRegex(Exception,'MERGE_CONFIRMATION_REFUSED'):self.merge()
    def test_api_cannot_review_force_merge_or_modify_rules(self):
        api=M.API(self.t.f.proposal,2,'synthetic','synthetic')
        with patch.object(M.http.client,'HTTPConnection') as connection:
            for method,path,body in [('POST','/pulls/2/reviews',{}),('POST','/pulls/2/merge',{'force_merge':True}),
                    ('PATCH','/branch_protections/main',{})]:
                with self.assertRaisesRegex(Exception,'MERGE_API_ROUTE_REFUSED'):api(method,path,body)
            connection.assert_not_called()

if __name__=='__main__':unittest.main()
