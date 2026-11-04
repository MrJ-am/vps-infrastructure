import json,tempfile,unittest
from pathlib import Path
import test_admission_orchestrator
import acceptance_pipeline as P

class Interrupted(BaseException):pass

class Adapter:
    def __init__(self):self.calls=[];self.remote={};self.interrupt=False;self.fail=False;self.wrong=False
    def execute(self,stage,directory,job,receipts):
        key=(job['id'],stage)
        if self.fail:raise TimeoutError('synthetic unavailable')
        if key not in self.remote:
            self.calls.append(key)
            self.remote[key]={'repository':job['capture']['proposal']['repository'],
                'head':('f'*40 if self.wrong else job['capture']['proposal']['head'])}
        if self.interrupt:raise Interrupted()
        return self.remote[key]

class Pipeline(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);root=Path(self.tmp.name)
        self.jobs=root/'jobs';self.jobs.mkdir(mode=0o700);self.state=root/'ledger';self.state.mkdir(mode=0o700)
        self.adapter=Adapter();self.now=1;self.job=self.add_job(1)
    def add_job(self,number):
        identifier=format(number,'064x');directory=self.jobs/identifier;directory.mkdir(mode=0o700)
        value={'schema_version':1,'id':identifier,'phase':'validated','capture':{
            'proposal_sha256':'b'*64,'proposal':{'repository':'mrjam-plateforme','head':'c'*40}}}
        P.O.save(directory/'state.json',value);return value
    def tick(self,stage):return P.tick(stage,self.jobs,self.state,self.adapter,clock=lambda:self.now)
    def ledger(self):return json.loads((self.state/self.job['id']/'state.json').read_bytes())
    def test_later_identities_cannot_skip_prerequisites(self):
        for stage in ['sync','merge','review']:self.assertEqual(self.tick(stage)['code'],'ACCEPTANCE_IDLE')
        self.assertEqual(self.adapter.calls,[]);self.assertEqual(list(self.state.iterdir()),[])
    def test_ordered_stages_persist_receipts_without_marking_deployed(self):
        for stage in P.STAGES:
            self.assertEqual(self.tick(stage)['code'],'ACCEPTANCE_STAGE_COMPLETE')
            self.assertEqual(self.tick(stage)['code'],'ACCEPTANCE_IDLE')
        self.assertEqual(len(self.adapter.calls),4)
        self.assertEqual(set(self.ledger()['receipts']),set(P.STAGES))
        self.assertEqual(P.O.read(self.jobs/self.job['id']/'state.json')['phase'],'validated')
    def test_process_death_after_remote_effect_resumes_same_identity(self):
        self.adapter.interrupt=True
        with self.assertRaises(Interrupted):self.tick('mirror')
        self.assertEqual(self.ledger()['inflight'],'mirror');self.assertEqual(self.ledger()['receipts'],{})
        self.assertEqual(self.tick('review')['code'],'ACCEPTANCE_IDLE')
        self.adapter.interrupt=False;self.assertEqual(self.tick('mirror')['code'],'ACCEPTANCE_STAGE_COMPLETE')
        self.assertEqual(len(self.adapter.calls),1)
    def test_transient_failure_does_not_block_another_job(self):
        self.adapter.fail=True;self.assertEqual(self.tick('mirror')['code'],'ACCEPTANCE_RETRY')
        other=self.add_job(2);self.adapter.fail=False
        self.assertEqual(self.tick('mirror')['job'],other['id']);self.assertEqual(self.ledger()['receipts'],{})
        self.now+=301;self.assertEqual(self.tick('mirror')['job'],self.job['id'])
    def test_other_commit_receipt_never_advances_next_identity(self):
        self.adapter.wrong=True;self.assertEqual(self.tick('mirror')['code'],'ACCEPTANCE_RESULT_BINDING_REFUSED')
        self.assertEqual(self.ledger()['receipts'],{});self.assertEqual(self.tick('review')['code'],'ACCEPTANCE_IDLE')
    def test_deployed_and_reserved_jobs_are_not_reaccepted(self):
        path=self.jobs/self.job['id']/'state.json'
        for phase,marker in [('deployed',None),('validated',{'schema_version':1,'plan_sha256':'d'*64,'proposal_sha256':'b'*64})]:
            v={**self.job,'phase':phase}
            if marker:v['promotion']=marker
            P.O.save(path,v);self.assertEqual(self.tick('mirror')['code'],'ACCEPTANCE_IDLE')
        self.assertEqual(self.adapter.calls,[])
    def test_forged_stage_order_refused(self):
        self.tick('mirror');value=self.ledger();value['receipts']={'merge':{}}
        P.O.save(self.state/self.job['id']/'state.json',value)
        with self.assertRaisesRegex(Exception,'ACCEPTANCE_RECEIPTS_ORDER_REFUSED'):self.tick('sync')

if __name__=='__main__':unittest.main()
