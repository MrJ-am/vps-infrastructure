import copy,unittest
from unittest.mock import patch
import test_source_observation
import validation_feedback as F

class Feedback(unittest.TestCase):
    def setUp(self):
        self.proposal={'repository':'mrjam-plateforme','repository_id':1437120781,'number':3,
            'draft':False,'branch':'synthetic','base':'a'*40,'head':'b'*40}
        self.policy={'accepted_proposals':['c'*64],'rules_revision':'d'*40,
            'sources':[{'repository':'MrJ-am/mrjam-plateforme','revision':'b'*40}], 'required_steps':['one','two']}
        self.envelope={'payload':{'proposal_sha256':'c'*64}}
        self.run={'id':4,'terminal':True,'status':'success','proposal_sha256':'c'*64,'rules_revision':'d'*40}
        self.credentials={'app_id':F.P.APP_ID,'owner_id':12571490,'slug':'synthetic',
            'private_key':'A'*1500,'permissions':F.P.A.PERMISSIONS}
        self.calls=[];self.rows=[];self.saved=None;self.moved=False;self.lost=False;self.bad_scope=False
    def request(self,path,token,method='GET',body=None):
        self.calls.append((method,path))
        if path.endswith('/access_tokens'):
            self.assertEqual(body,{'repository_ids':[1437120781],'permissions':F.PERMISSIONS})
            return 201,{'token':'synthetic-token','permissions':{} if self.bad_scope else F.PERMISSIONS}
        if method=='DELETE':return 204,None
        if '/pulls/' in path:
            repo={'id':1437120781,'full_name':'MrJ-am/mrjam-plateforme'}
            return 200,{'number':3,'draft':False,'state':'open','base':{'ref':'main','sha':'a'*40,'repo':repo},
                'head':{'ref':'synthetic','sha':('e' if self.moved else 'b')*40,'repo':repo}}
        if method=='GET':return 200,self.rows
        self.assertEqual(path,'/repos/MrJ-am/mrjam-plateforme/statuses/'+'b'*40)
        self.saved={**body,'id':9,'creator':{'login':'synthetic[bot]','type':'Bot'}}
        self.rows=[self.saved]
        if self.lost:raise TimeoutError('synthetic lost response')
        return 201,self.saved
    def publish(self,verified=True):
        with patch.object(F.P.A,'jwt',return_value='synthetic-jwt'):
            return F.publish(self.proposal,self.run,self.policy,self.envelope,self.credentials,
                verify=lambda envelope,policy:verified,request=self.request)
    def test_signed_success_targets_exact_commit_and_revokes_scoped_token(self):
        result=self.publish();self.assertFalse(result['deployment_authorized'])
        self.assertEqual(result['head'],'b'*40);self.assertEqual(result['status_id'],9)
        self.assertEqual(self.saved['target_url'],'https://forge.mrj.am/MrJ-am/mrjam-validation/actions/runs/4')
        self.assertEqual(self.calls[-1],('DELETE','/installation/token'))
    def test_invalid_signature_never_issues_token(self):
        with self.assertRaisesRegex(Exception,'FEEDBACK_SIGNATURE_REFUSED'):self.publish(False)
        self.assertEqual(self.calls,[])
    def test_wrong_run_digest_rules_or_status_never_issues_token(self):
        original=copy.deepcopy(self.run)
        for field,value in [('proposal_sha256','e'*64),('rules_revision','f'*40),('status','failure'),('terminal',False)]:
            self.run={**original,field:value}
            with self.assertRaisesRegex(Exception,'FEEDBACK_RUN_REFUSED'):self.publish()
        self.assertEqual(self.calls,[])
    def test_different_source_never_issues_token(self):
        self.policy['sources'][0]['revision']='f'*40
        with self.assertRaisesRegex(Exception,'FEEDBACK_SOURCE_REFUSED'):self.publish()
        self.assertEqual(self.calls,[])
    def test_moved_head_has_no_status_and_token_is_revoked(self):
        self.moved=True
        with self.assertRaisesRegex(Exception,'FEEDBACK_PROPOSAL_CHANGED'):self.publish()
        self.assertIsNone(self.saved);self.assertEqual(self.calls[-1],('DELETE','/installation/token'))
    def test_lost_response_is_reconciled_without_second_status(self):
        self.lost=True
        with self.assertRaises(TimeoutError):self.publish()
        self.assertEqual(self.calls[-1],('DELETE','/installation/token'))
        self.lost=False;result=self.publish();self.assertTrue(result['recovered_existing'])
        self.assertEqual(sum(m=='POST' and '/statuses/' in p for m,p in self.calls),1)
    def test_another_principal_cannot_supply_our_publication_receipt(self):
        self.publish();self.rows[0]['creator']['login']='another[bot]';self.calls=[]
        self.assertFalse(self.publish()['recovered_existing'])
        self.assertEqual(sum(m=='POST' and '/statuses/' in p for m,p in self.calls),1)
    def test_broader_token_is_refused_and_revoked(self):
        self.bad_scope=True
        with self.assertRaisesRegex(Exception,'FEEDBACK_PERMISSIONS_REFUSED'):self.publish()
        self.assertEqual(self.calls[-1],('DELETE','/installation/token'));self.assertIsNone(self.saved)

if __name__=='__main__':unittest.main()
