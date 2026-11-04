"""Fixed tree peel semantic regression; invented API data, no native proof."""
from pathlib import Path
import sys,unittest,copy
sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_api_projection as fixtures
import api_projection_v2 as A
import read_transport_v3 as T
import contract as V

class Tests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.fixtures.Tests('runTest');self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.api=fixtures.API(self.f)
        self.api.data[self.api.pull]['requested_reviewers']=[{'id':101}]
        head=self.f.observed['head_sha'];self.path=self.api.root+'/git/trees/'+head+'%5E%7Btree%7D?page=1&per_page=1'
        self.api.data[self.api.root+'/git/commits/'+head+'?stat=false&verification=false&files=false']['commit']['tree']['sha']=head
        self.api.data[self.path]={'sha':self.f.observed['head_tree'],'truncated':True,'tree':[{'ignored':'not an inventory proof'}]}
    def collect(self):return A.collect(self.api,self.f.policy,12,self.f.policy['previous_generation'],now=self.f.now)
    def test_actual_commit_shape_cannot_masquerade_as_tree(self):
        observed=self.collect();self.assertEqual(observed,self.f.observed);self.assertIn(self.path,self.api.calls)
    def test_unpeeled_commit_and_invalid_digest_refused(self):
        for sha in (self.f.observed['head_sha'],'not-a-git-object',True):
            self.api.data[self.path]['sha']=sha
            with self.subTest(sha=sha),self.assertRaises(V.Refused):self.collect()
    def test_participants_are_not_unresolved_requests(self):
        self.assertEqual(self.collect()['requested_reviewer_ids'],[])
        self.api.data[self.api.pull]['requested_reviewers'].append({'id':102})
        with self.assertRaisesRegex(V.Refused,'REVIEW_PARTICIPANTS_CHANGED'):self.collect()
    def test_actual_pending_request_remains_refused(self):
        self.api.rows[0]['state']='REQUEST_REVIEW'
        with self.assertRaisesRegex(V.Refused,'REQUESTED_REVIEW_OUTSTANDING'):self.collect()
    def test_dismissed_decisions_do_not_create_active_participant(self):
        rows=[{**self.api.rows[0],'reviewer_id':101,'dismissed':True}]
        self.assertEqual(A.pending_requests([],rows),[])
        with self.assertRaises(V.Refused):A.pending_requests([101],rows)
    def test_stale_head_still_refused(self):
        self.api.changed=lambda value:value['head'].update(sha='2'*40)
        with self.assertRaisesRegex(V.Refused,'PULL_REQUEST_CHANGED'):self.collect()
    def test_route_only_accepts_fixed_hex_commit_tree_peel(self):
        transport=T.Transport('invented-test-token-no-secret','mrjam-plateforme',12)
        self.assertTrue(transport.allowed(self.path))
        for path in (self.path.replace('%5E%7Btree%7D',''),self.path.replace('%5E%7Btree%7D','%5E%7Bcommit%7D'),self.path+'&recursive=true',self.path.replace('per_page=1','per_page=500'),self.path.replace('e'*40,'main'),self.path.replace('mrjam-plateforme','vision')):
            with self.subTest(path=path):self.assertFalse(transport.allowed(path))
    def test_no_candidate_url_is_followed(self):
        self.api.data[self.path]['url']='https://elsewhere.invalid/private'
        self.collect();self.assertTrue(all(p.startswith('/api/v1/') for p in self.api.calls))

class HTTPRouteTests(unittest.TestCase):
    def test_fixed_tree_peel_is_sent_encoded_to_loopback(self):
        import test_read_transport_v2 as http_fixture
        from unittest.mock import patch
        change=patch.object(http_fixture,'T',T);change.start();self.addCleanup(change.stop)
        fixture=http_fixture.Tests('runTest');fixture.setUp();self.addCleanup(fixture.tearDown)
        path=fixture.transport.root+'/git/trees/'+'a'*40+'%5E%7Btree%7D?page=1&per_page=1'
        fixture.body=b'{"sha":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}'
        value,_=fixture.transport.get(path)
        self.assertEqual(value['sha'],'b'*40)
        self.assertEqual(fixture.requests[0][0],path)

if __name__=='__main__':unittest.main()
