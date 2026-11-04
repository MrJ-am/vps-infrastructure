import importlib.util,sys,unittest
from pathlib import Path
from unittest.mock import patch
HERE=Path(__file__).resolve().parent
for name,filename in [('github_app_auth','github-app-receive.py'),('github_proposals','github-proposals.py')]:
    s=importlib.util.spec_from_file_location(name,HERE/filename);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m)
import source_observation as O

class Observation(unittest.TestCase):
    def test_draft_refused_before_issuing_token(self):
        proposal={'repository':'mrjam-plateforme','repository_id':1437120781,'number':2,'draft':True,
            'branch':'synthetic','base':'a'*40,'head':'b'*40}
        credentials={'app_id':O.P.APP_ID,'owner_id':12571490,'slug':'synthetic','private_key':'A'*1500,'permissions':O.P.A.PERMISSIONS}
        with patch.object(O.P.A,'jwt') as jwt:
            with self.assertRaisesRegex(O.S.Refused,'PROPOSAL_SCOPE_REFUSED'):O.observe(proposal,credentials)
            jwt.assert_not_called()
    def exercise(self,change=None):
        proposal={'repository':'mrjam-plateforme','repository_id':1437120781,'number':2,'draft':False,
            'branch':'synthetic','base':'a'*40,'head':'b'*40}
        credentials={'app_id':O.P.APP_ID,'owner_id':12571490,'slug':'synthetic','private_key':'A'*1500,'permissions':O.P.A.PERMISSIONS}
        calls=[];reads=0
        def request(path,token,method='GET',body=None):
            nonlocal reads
            calls.append((method,path))
            if method=='POST':
                self.assertEqual(body,{'repository_ids':[1437120781],'permissions':O.P.READ_PERMISSIONS})
                return 201,{'token':'synthetic-token','permissions':O.P.READ_PERMISSIONS}
            if method=='DELETE':return 204,None
            if '/git/commits/' in path:
                return 200,{'sha':'c'*40 if change=='commit' else 'b'*40,'tree':{'sha':'invalid' if change=='tree' else 'd'*40}}
            reads+=1;repo={'id':1437120781,'full_name':'MrJ-am/mrjam-plateforme'}
            return 200,{'number':2,'draft':False,'state':'open','base':{'ref':'main','sha':'a'*40,'repo':repo},
                'head':{'ref':'synthetic','sha':'e'*40 if change=='head' and reads==2 else 'b'*40,'repo':repo}}
        try:
            with patch.object(O.P.A,'jwt',return_value='synthetic-jwt'):
                result=O.observe(proposal,credentials,request)
                self.assertEqual(result,{'repository':'MrJ-am/mrjam-plateforme','revision':'b'*40,'tree_sha':'d'*40})
        finally:self.assertEqual(calls[-1],('DELETE','/installation/token'))
    def test_fresh_exact_tree_with_read_token_revoked(self):self.exercise()
    def test_different_commit_refused(self):
        with self.assertRaisesRegex(O.S.Refused,'COMMIT_TREE_REFUSED'):self.exercise('commit')
    def test_malformed_tree_refused(self):
        with self.assertRaisesRegex(O.S.Refused,'COMMIT_TREE_REFUSED'):self.exercise('tree')
    def test_head_moved_during_observation_refused(self):
        with self.assertRaisesRegex(O.S.Refused,'PROPOSAL_OBSERVATION_CHANGED'):self.exercise('head')
if __name__=='__main__':unittest.main()
