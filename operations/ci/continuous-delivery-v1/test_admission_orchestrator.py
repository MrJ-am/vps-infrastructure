import copy,json,tempfile,unittest
from pathlib import Path
import test_intake_queue as T
import admission_orchestrator as O

class Interrupted(BaseException):pass

def ready(number=1):
    proposal=T.proposal(number=number)
    return {'job':{'key':T.Q.key(proposal),'proposal':json.dumps(proposal),'receipt':format(number,'064x'),'visible':1},
        'result':'d'*64,'base_sha256':'a'*64,'base_policy_sha256':'b'*64}

class Adapter:
    def __init__(self):
        self.calls=[];self.decisions=[];self.current_base=True;self.terminal=True
        self.status='success';self.posts=0;self.remote=None;self.interrupt_post=False;self.fail_build=False
    def check_ready(self,item):
        assert set(item)=={'job','result','base_sha256','base_policy_sha256'}
        assert T.Q.key(json.loads(item['job']['proposal']))==item['job']['key']
    def current(self,value):return self.current_base
    def capture(self,path,value):self.calls.append('capture');return {'proposal_sha256':'e'*64}
    def construct(self,path,value):
        self.calls.append('construct')
        if self.fail_build:raise O.W.Q.S.Refused('CONSTRUCTOR_TEMPORARILY_UNAVAILABLE')
        return '/nix/store/'+'a'*32+'-synthetic'
    def observe(self,value):self.calls.append('observe')
    def admit(self,path,value):self.calls.append('admit')
    def run_boundary(self,value):return 2
    def dispatch(self,value):
        self.calls.append('dispatch');assert value['after_id']==2
        if self.remote is None:
            self.posts+=1;self.remote={'id':3,'terminal':False,'status':'waiting'}
            if self.interrupt_post:raise Interrupted()
        return self.remote
    def poll(self,value):return {'id':3,'terminal':self.terminal,'status':self.status}
    def capture_artifacts(self,path,value):self.calls.append('signed-capture');return {'signature_verified':True}
    def feedback(self,path,value):self.calls.append('feedback');return {'status_id':9,'deployment_authorized':False}
    def decision(self,value,action):self.decisions.append((value['id'],action))

class Orchestration(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.adapter=Adapter();self.now=10;self.ready=[ready()]
    def tick(self):return O.tick(self.root,self.ready,self.adapter,clock=lambda:self.now)
    def state(self,item=None):return O.read(self.root/'jobs'/O.identity(item or self.ready[0])/'state.json')
    def reach(self,phase):
        for _ in range(10):
            result=self.tick()
            if result.get('phase')==phase:return result
            self.now+=1
        self.fail('phase not reached: '+phase)
    def test_complete_ci_requires_signed_capture_and_keeps_review_pending(self):
        self.reach('validated');state=self.state()
        self.assertTrue(state['artifacts']['signature_verified']);self.assertEqual(self.adapter.posts,1)
        self.assertEqual(self.adapter.decisions,[]);self.assertEqual(self.tick()['phase'],'validated')
        self.assertEqual(self.state()['feedback']['status_id'],9)
        self.assertEqual(self.tick()['code'],'ORCHESTRATOR_IDLE')
        self.assertEqual(self.adapter.calls,['capture','construct','observe','admit','observe','dispatch','signed-capture','feedback'])
    def test_lost_dispatch_result_resumes_exact_run_without_new_post(self):
        self.reach('dispatching');self.adapter.interrupt_post=True
        with self.assertRaises(Interrupted):self.tick()
        self.assertEqual(self.state()['phase'],'dispatching')
        self.assertEqual(self.tick()['phase'],'running');self.assertEqual(self.adapter.posts,1)
    def test_validity_is_fixed_across_constructor_retry(self):
        self.reach('captured');validity=copy.deepcopy(self.state()['validity'])
        self.adapter.fail_build=True;self.assertEqual(self.tick()['code'],'CONSTRUCTOR_TEMPORARILY_UNAVAILABLE')
        self.now+=301;self.adapter.fail_build=False
        self.assertEqual(self.tick()['phase'],'constructed');self.assertEqual(self.state()['validity'],validity)
    def test_old_base_before_admission_requeues_without_ci(self):
        self.reach('constructed');self.adapter.current_base=False
        self.assertEqual(self.tick()['phase'],'obsolete');self.assertEqual(self.adapter.posts,0)
        self.assertEqual(self.adapter.decisions[-1][1],'reprepare')
    def test_running_ci_finishes_before_obsolete_input_can_be_retired(self):
        self.reach('running');self.adapter.current_base=False;self.adapter.terminal=False
        self.assertEqual(self.tick()['phase'],'running');self.assertEqual(self.adapter.decisions,[])
        self.assertEqual(self.state()['next_attempt'],self.now+30)
        self.now+=31;self.adapter.terminal=True
        self.assertEqual(self.tick()['phase'],'obsolete');self.assertNotIn('signed-capture',self.adapter.calls)
    def test_other_job_cannot_replace_running_input(self):
        self.reach('running');self.adapter.terminal=False;self.ready.append(ready(2))
        self.assertEqual(self.tick()['phase'],'running');self.now+=1
        self.assertEqual(self.tick()['code'],'ORCHESTRATOR_IDLE')
        self.assertEqual(self.state(self.ready[1])['phase'],'pending')
    def test_construction_failure_does_not_block_other_project(self):
        self.reach('captured');self.adapter.fail_build=True;self.tick()
        self.now+=1;self.ready.append(ready(2));result=self.tick()
        self.assertEqual(result['job'],O.identity(self.ready[1]));self.assertEqual(result['phase'],'captured')
    def test_failed_ci_cannot_become_deployable(self):
        self.reach('running');self.adapter.status='failure'
        self.assertEqual(self.tick()['phase'],'failed')
        self.assertNotIn('signed-capture',self.adapter.calls);self.assertEqual(self.adapter.decisions[-1][1],'captured')
    def test_visibility_changes_do_not_duplicate_job(self):
        self.reach('captured');self.ready[0]['job']['visible']=0
        self.tick();self.assertEqual(len(list((self.root/'jobs').iterdir())),1)
    def test_new_base_invalidates_validated_but_unpromoted_job(self):
        self.reach('validated');self.adapter.current_base=False
        self.assertEqual(self.tick()['phase'],'obsolete');self.assertEqual(self.adapter.decisions[-1][1],'reprepare')
    def test_partial_initial_journal_is_recovered_before_any_action(self):
        jobs=self.root/'jobs';jobs.mkdir(mode=0o700);job=jobs/O.identity(self.ready[0]);job.mkdir(mode=0o700)
        (job/'state.next').write_text('{"schema_version":')
        self.assertEqual(self.tick()['phase'],'captured');self.assertEqual(self.adapter.calls,['capture'])
    def test_feedback_failure_retries_without_repeating_validation(self):
        self.reach('validated')
        original=self.adapter.feedback
        def unavailable(path,value):raise O.W.Q.S.Refused('FEEDBACK_TEMPORARILY_UNAVAILABLE')
        self.adapter.feedback=unavailable
        self.assertEqual(self.tick()['code'],'FEEDBACK_TEMPORARILY_UNAVAILABLE')
        self.assertEqual(self.state()['phase'],'validated');self.assertNotIn('feedback',self.state())
        self.now+=301;self.adapter.feedback=original
        self.assertEqual(self.tick()['phase'],'validated');self.assertEqual(self.adapter.posts,1)
        self.assertEqual(self.adapter.calls.count('signed-capture'),1)
    def test_obsolete_validation_never_publishes_success_feedback(self):
        self.reach('validated');self.adapter.current_base=False
        self.assertEqual(self.tick()['phase'],'obsolete');self.assertNotIn('feedback',self.adapter.calls)
    def mark_promotion(self):
        self.reach('validated');value=self.state()
        value['promotion']={'schema_version':1,'plan_sha256':'f'*64,'proposal_sha256':'e'*64}
        O.save(self.root/'jobs'/value['id']/'state.json',value)
    def test_crash_after_base_change_never_retires_promoting_job(self):
        self.mark_promotion();self.adapter.current_base=False;self.now+=1000000
        self.assertEqual(self.tick()['code'],'ORCHESTRATOR_DELIVERY_PENDING')
        self.assertEqual(self.state()['phase'],'validated');self.assertEqual(self.adapter.decisions,[])
        self.assertNotIn('feedback',self.adapter.calls)
    def test_pending_delivery_does_not_block_other_project_ci(self):
        self.mark_promotion();self.ready.append(ready(2));self.now+=1
        result=self.tick();self.assertEqual(result['job'],O.identity(self.ready[1]))
        self.assertEqual(result['phase'],'captured');self.assertEqual(self.state()['phase'],'validated')
    def test_malformed_marker_is_not_accepted_as_delivery_authority(self):
        self.mark_promotion();value=self.state();value['promotion']['proposal_sha256']='a'*64
        O.save(self.root/'jobs'/value['id']/'state.json',value)
        with self.assertRaisesRegex(Exception,'ORCHESTRATOR_PROMOTION_MARKER_REFUSED'):self.tick()

if __name__=='__main__':unittest.main()
