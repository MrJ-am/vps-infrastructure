"""Review ID is decision order; edit timestamps cannot reverse a later decision."""
from pathlib import Path
import sys,unittest,copy
sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_review_contract as fixtures
import review_contract_v2 as R
import contract as V
class Tests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.Tests('runTest');self.f.setUp();self.addCleanup(self.f.doCleanups)
    def bind(self):
        f=self.f
        return R.bind_review(f.envelope,f.fixture.policy,f.policy,f.observed,f.manifest,now=f.now,executable=fixtures.fixtures.OPENSSL)
    def test_edit_of_old_approval_cannot_hide_newer_rejection(self):
        f=self.f;old=f.observed['reviews'][0];old['updated_at']=f.now
        f.observed['reviews'].append({**old,'id':2,'updated_at':f.now-1,'state':'REQUEST_CHANGES'})
        with self.assertRaisesRegex(V.Refused,'REVIEW_REQUEST_UNRESOLVED'):self.bind()
    def test_newer_approval_not_reversed_by_edit_of_older_rejection(self):
        f=self.f;old=f.observed['reviews'][0];old.update(state='REQUEST_CHANGES',updated_at=f.now)
        f.observed['reviews'].append({**old,'id':2,'updated_at':f.now-1,'state':'APPROVED'})
        self.assertEqual(self.bind()['review_id'],2)
    def test_dismissed_newer_approval_not_resurrected_by_old_edit(self):
        f=self.f;old=f.observed['reviews'][0];old['updated_at']=f.now
        f.observed['reviews'].append({**old,'id':2,'updated_at':f.now-1,'dismissed':True})
        with self.assertRaisesRegex(V.Refused,'HUMAN_MANIFEST_REVIEW_REQUIRED'):self.bind()
    def test_other_rejection_survives_dismissed_newer_approval(self):
        f=self.f;old=f.observed['reviews'][0]
        f.observed['reviews'].extend([
            {**old,'id':2,'reviewer_id':999,'state':'REQUEST_CHANGES'},
            {**old,'id':3,'reviewer_id':999,'state':'APPROVED','dismissed':True}])
        with self.assertRaisesRegex(V.Refused,'REVIEW_REQUEST_UNRESOLVED'):self.bind()
    def test_other_request_survives_dismissed_newer_approval(self):
        f=self.f;old=f.observed['reviews'][0]
        f.observed['reviews'].extend([
            {**old,'id':2,'reviewer_id':999,'state':'REQUEST_REVIEW'},
            {**old,'id':3,'reviewer_id':999,'state':'APPROVED','dismissed':True}])
        with self.assertRaisesRegex(V.Refused,'REVIEW_REQUEST_UNRESOLVED'):self.bind()
    def test_dismissed_rejection_does_not_block_other_valid_approval(self):
        f=self.f;old=f.observed['reviews'][0]
        f.observed['reviews'].append({**old,'id':2,'reviewer_id':999,
            'state':'REQUEST_CHANGES','dismissed':True})
        self.assertEqual(self.bind()['review_id'],old['id'])
if __name__=='__main__':unittest.main()
