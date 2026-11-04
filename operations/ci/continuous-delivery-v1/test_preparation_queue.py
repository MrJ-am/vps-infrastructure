import json,tempfile,unittest
from pathlib import Path
import test_admission_orchestrator
import preparation_queue as Q

class Interrupted(BaseException):pass
class Adapter:
    def __init__(self):self.calls=[];self.fail=False;self.interrupt=False;self.env={'system':'synthetic'};self.environments=0
    def environment(self):self.environments+=1;return self.env
    def supports(self,job):return job['capture']['proposal']['repository']=='mrjam-plateforme'
    def prepare(self,directory,work,job,environment):
        self.calls.append((job['id'],str(work)))
        if self.fail:raise TimeoutError()
        if self.interrupt:raise Interrupted()
        return {'job':job['id'],'proposal_sha256':job['capture']['proposal_sha256'],
            'environment_sha256':Q.O.sha(Q.O.encode(environment)),'deployment_authorized':False}
class Queue(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name);self.jobs=root/'jobs';self.state=root/'state'
        self.jobs.mkdir(mode=0o700);self.state.mkdir(mode=0o700);self.a=Adapter();self.now=1;self.job=self.add_job(1)
    def add_job(self,n,repository='mrjam-plateforme',phase='validated'):
        j={'schema_version':1,'id':format(n,'064x'),'phase':phase,
            'capture':{'proposal_sha256':'b'*64,'proposal':{'repository':repository}}}
        d=self.jobs/j['id'];d.mkdir(mode=0o700);Q.O.save(d/'state.json',j);return j
    def tick(self):return Q.tick(self.jobs,self.state,self.a,clock=lambda:self.now)
    def work(self):return self.state/self.job['id']/Q.O.sha(Q.O.encode(self.a.env))
    def test_preparation_is_durable_and_does_not_deploy(self):
        self.assertEqual(self.tick()['code'],'PREPARATION_COMPLETE');self.assertEqual(self.tick()['code'],'PREPARATION_IDLE')
        self.assertEqual(len(self.a.calls),1);self.assertEqual(Q.O.read(self.jobs/self.job['id']/'state.json')['phase'],'validated')
        self.assertTrue((self.work()/'ready.json').exists())
    def test_active_ci_prevents_memory_overlap_before_environment_read(self):
        self.add_job(2,phase='running');self.assertEqual(self.tick()['code'],'PREPARATION_CI_BUSY')
        self.assertEqual(self.a.environments,0);self.assertEqual(self.a.calls,[])
    def test_missing_vise_recipe_never_blocks_another_project(self):
        self.job['capture']['proposal']['repository']='etp-vie-affective';Q.O.save(self.jobs/self.job['id']/'state.json',self.job)
        other=self.add_job(2);self.assertEqual(self.tick()['job'],other['id']);self.assertEqual(len(self.a.calls),1)
    def test_failed_job_yields_to_next_job_until_retry(self):
        self.a.fail=True;self.assertEqual(self.tick()['code'],'PREPARATION_RETRY')
        other=self.add_job(2);self.a.fail=False;self.assertEqual(self.tick()['job'],other['id'])
        self.now=302;self.assertEqual(self.tick()['job'],self.job['id'])
    def test_process_death_reuses_same_work_directory(self):
        self.a.interrupt=True
        with self.assertRaises(Interrupted):self.tick()
        self.a.interrupt=False;self.assertEqual(self.tick()['code'],'PREPARATION_COMPLETE')
        self.assertEqual(self.a.calls[0],self.a.calls[1])
    def test_environment_change_uses_a_new_binding(self):
        self.tick();old=self.work();self.a.env={'system':'new-synthetic'};self.tick()
        self.assertNotEqual(old,self.work());self.assertEqual(len(self.a.calls),2)
    def test_missing_ready_receipt_is_reconstructed(self):
        self.tick();(self.work()/'ready.json').unlink();self.assertEqual(self.tick()['code'],'PREPARATION_COMPLETE')
    def test_reserved_and_deployed_jobs_are_skipped(self):
        self.job.update(phase='deployed');Q.O.save(self.jobs/self.job['id']/'state.json',self.job)
        self.assertEqual(self.tick()['code'],'PREPARATION_IDLE');self.assertEqual(self.a.calls,[])

if __name__=='__main__':unittest.main()
