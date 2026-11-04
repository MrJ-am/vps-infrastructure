import base64,copy,json,unittest
from pathlib import Path
import validation_dispatch as D
from source_snapshot import Refused

PROPOSAL='b'*64;RULES='a'*40
def run(identifier=3,digest=PROPOSAL,status='waiting'):
    return {'id':identifier,'workflow_id':D.WORKFLOW,'commit_sha':RULES,'trigger_event':'workflow_dispatch',
        'event_payload':json.dumps({'inputs':{'proposal_digest':digest}}),
        'repository':{'full_name':'MrJ-am/mrjam-validation'},'status':status}

class Remote:
    def __init__(self):self.rows=[];self.posts=0;self.rules=RULES;self.lose_response=False
    def request(self,method,path,body=None):
        if method=='GET' and '/actions/runs?' in path:return {'workflow_runs':self.rows}
        if method=='GET' and '/actions/runs/' in path:
            return copy.deepcopy(next(r for r in self.rows if r['id']==int(path.rsplit('/',1)[1])))
        if path.endswith('/branches/main'):return {'commit':{'id':self.rules}}
        if '/contents/' in path:
            raw=(Path(__file__).resolve().parents[2]/'forgejo/independent-validation.yml').read_bytes()
            return {'encoding':'base64','content':base64.b64encode(raw).decode()}
        if method=='POST':
            assert body=={'ref':'main','inputs':{'proposal_digest':PROPOSAL},'return_run_info':True}
            self.posts+=1;self.rows.insert(0,run(3+self.posts))
            if self.lose_response:raise TimeoutError('invented lost HTTP response')
            return {'id':self.rows[0]['id'],'run_number':self.posts,'jobs':[]}
        raise AssertionError(path)

class Dispatch(unittest.TestCase):
    def test_exact_dispatch_and_recovery_do_not_repeat_post(self):
        r=Remote();first=D.ensure(r.request,PROPOSAL,RULES)
        self.assertFalse(first['recovered_existing']);self.assertFalse(first['deployment_authorized'])
        second=D.ensure(r.request,PROPOSAL,RULES)
        self.assertTrue(second['recovered_existing']);self.assertEqual(r.posts,1)
        self.assertEqual(first['id'],second['id'])
    def test_lost_post_response_recovers_by_server_recorded_digest(self):
        r=Remote();r.lose_response=True
        with self.assertRaises(TimeoutError):D.ensure(r.request,PROPOSAL,RULES)
        recovered=D.ensure(r.request,PROPOSAL,RULES)
        self.assertTrue(recovered['recovered_existing']);self.assertEqual(r.posts,1)
    def test_other_proposal_run_is_not_reused(self):
        r=Remote();r.rows=[run(1,digest='c'*64,status='success')]
        result=D.ensure(r.request,PROPOSAL,RULES)
        self.assertEqual(r.posts,1);self.assertNotEqual(result['id'],1)
    def test_changed_validation_main_refused_before_post(self):
        r=Remote();r.rules='d'*40
        with self.assertRaisesRegex(Refused,'VALIDATION_RULES_MOVED'):D.ensure(r.request,PROPOSAL,RULES)
        self.assertEqual(r.posts,0)
    def test_lookalike_run_from_other_repository_refused(self):
        r=Remote();row=run();row['repository']['full_name']='someone/other';r.rows=[row]
        with self.assertRaisesRegex(Refused,'RUN_REPOSITORY_REFUSED'):D.ensure(r.request,PROPOSAL,RULES)
        self.assertEqual(r.posts,0)
    def test_extra_inputs_are_not_an_exact_validation(self):
        row=run();row['event_payload']=json.dumps({'inputs':{'proposal_digest':PROPOSAL,'skip':True}})
        self.assertIsNone(D.identify(row,PROPOSAL,RULES))
    def test_failed_run_reported_as_failed_without_repeated_ci(self):
        r=Remote();r.rows=[run(status='failure')]
        result=D.ensure(r.request,PROPOSAL,RULES)
        self.assertTrue(result['terminal']);self.assertEqual(result['status'],'failure');self.assertEqual(r.posts,0)
    def test_wrong_dispatch_response_binding_is_refused(self):
        r=Remote()
        def request(method,path,body=None):
            result=r.request(method,path,body)
            if method=='GET' and '/actions/runs/' in path:result['event_payload']=json.dumps({'inputs':{'proposal_digest':'c'*64}})
            return result
        with self.assertRaisesRegex(Refused,'DISPATCH_INPUT_CHANGED'):D.ensure(request,PROPOSAL,RULES)
    def test_prior_validation_cannot_satisfy_a_new_submission(self):
        r=Remote();r.rows=[run(1,status='success')]
        result=D.ensure(r.request,PROPOSAL,RULES,after_id=1)
        self.assertEqual(r.posts,1);self.assertGreater(result['id'],1)
        recovered=D.ensure(r.request,PROPOSAL,RULES,after_id=1)
        self.assertTrue(recovered['recovered_existing']);self.assertEqual(r.posts,1)
    def test_unordered_remote_history_is_refused(self):
        r=Remote();r.rows=[run(1,digest='c'*64),run(2)]
        with self.assertRaisesRegex(Refused,'RUN_ORDER_CHANGED'):D.find(r.request,PROPOSAL,RULES)

if __name__=='__main__':unittest.main()
