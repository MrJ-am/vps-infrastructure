"""Invented Forgejo responses, real validation signatures; no API write."""
import copy
from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_api_projection as fixtures
import recheck as C
import contract as V

class Tests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.fixtures.Tests('runTest');self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.binding=self.f.bind();self.api=fixtures.API(self.f)
        self.review_path=self.api.pull+'/reviews/1'
        self.api.data[self.review_path]=copy.deepcopy(self.api.rows[0])
    def before(self):
        f=self.f
        return C.before_merge(self.api,f.envelope,f.fixture.policy,f.policy,self.binding,f.manifest,now=f.now,executable=fixtures.fixtures.fixtures.OPENSSL)
    def merged(self):
        p=self.api.data[self.api.pull];p.update(state='closed',merged=True,merge_commit_sha=self.binding['head_sha'])
        p['base']['sha']=self.binding['head_sha']
        self.api.data[self.api.root+'/branches/main']['commit']['id']=self.binding['head_sha']
    def after(self):return C.after_merge(self.api,self.f.policy,self.binding,now=self.f.now)
    def test_full_before_collection_and_final_individual_read(self):
        self.assertEqual(self.before(),self.binding)
        self.assertEqual(self.api.calls[-1],self.review_path)
    def test_review_withdrawn_after_page_collection_refused(self):
        self.api.data[self.review_path]['dismissed']=True
        with self.assertRaisesRegex(V.Refused,'SELECTED_REVIEW_CHANGED'):self.before()
    def test_body_or_update_changed_without_head_change_refused(self):
        for key,value in (('body','withdrawn'),('updated_at','2026-01-01T00:00:00Z'),('user',{'id':202}),('official',False)):
            self.api.data[self.review_path]={**self.api.rows[0],key:value}
            with self.subTest(key=key),self.assertRaisesRegex(V.Refused,'SELECTED_REVIEW_CHANGED'):self.before()
    def test_new_change_request_is_not_hidden_by_selected_approval(self):
        self.api.rows.append({**self.api.rows[0],'id':2,'user':{'id':102},'state':'REQUEST_CHANGES'})
        with self.assertRaisesRegex(V.Refused,'REVIEW_REQUEST_UNRESOLVED'):self.before()
    def test_changed_unsigned_binding_and_expired_binding_refused(self):
        self.binding['manifest_sha256']='0'*64
        with self.assertRaises(V.Refused):self.before()
        self.binding=self.f.bind();self.binding['expires_at']=self.f.now
        with self.assertRaises(V.Refused):self.before()
    def test_expected_ff_observed_without_authorization(self):
        self.merged();result=self.after()
        self.assertEqual(result['head_sha'],self.binding['head_sha'])
        self.assertNotIn('production_authorized',result)
    def test_merge_commit_or_main_movement_refused(self):
        self.merged();self.api.data[self.api.pull]['merge_commit_sha']='2'*40
        with self.assertRaisesRegex(V.Refused,'MERGE_RESULT'):self.after()
        self.merged();self.api.data[self.api.root+'/branches/main']['commit']['id']='2'*40
        with self.assertRaisesRegex(V.Refused,'MERGED_MAIN_CHANGED'):self.after()
    def test_approval_revoked_after_merge_withholds_observation(self):
        self.merged();self.api.data[self.review_path]['dismissed']=True
        with self.assertRaisesRegex(V.Refused,'SELECTED_REVIEW_CHANGED'):self.after()

if __name__=='__main__':unittest.main()
