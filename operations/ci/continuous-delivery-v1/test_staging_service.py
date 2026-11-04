import unittest
from types import SimpleNamespace
from unittest.mock import patch
import test_promotion_enqueue as F
import staging_service as S

class Handoff(unittest.TestCase):
    def setUp(self):
        self.f=F.Enqueue();self.f.setUp();self.addCleanup(self.f.doCleanups)
        f=self.f;directory=f.f.acceptance/f.job['id'];directory.mkdir(mode=0o700)
        S.O.save(directory/'state.json',f.ledger);S.O.save(f.f.jobs/f.job['id']/'state.json',f.job)
        for target,value in [('ACCEPTANCE',f.f.acceptance),('JOBS',f.f.jobs),('PROMOTION',f.state)]:
            p=patch.object(S,target,value);p.start();self.addCleanup(p.stop)
        patches=[patch.object(S.S,'Adapter',return_value=SimpleNamespace(plan=f.stage)),
            patch.object(S.T,'stage',return_value={'code':'STAGING_READY'}),
            patch.object(S.N,'enqueue',return_value={'code':'PROMOTION_PLAN_ENQUEUED'}),
            patch.object(S.V,'verify',return_value=f.stage['staged']['slots']['green']),patch.object(S.Gate,'ready')]
        mocks=[]
        for p in patches:mocks.append(p.start());self.addCleanup(p.stop)
        _,self.stage,self.enqueue,self.verify,self.ready=mocks
        self.driver=S.Driver(f.f.state,'synthetic-observer')
    def test_synced_acceptance_hands_plan_to_promotion_with_fresh_callbacks(self):
        f=self.f;self.assertEqual(self.driver.stage(f.stage)['code'],'PROMOTION_PLAN_ENQUEUED')
        args=self.enqueue.call_args
        self.assertEqual(args.args[3],f.plan)
        args.kwargs['authorize'](f.plan);args.kwargs['ready']()
        self.verify.assert_called_once_with(f.plan,'synthetic-observer')
        self.ready.assert_called_once_with(f.f.state,f.job)
    def test_incomplete_acceptance_does_not_create_promotion(self):
        f=self.f;f.ledger['receipts'].pop('sync');S.O.save(f.f.acceptance/f.job['id']/'state.json',f.ledger)
        self.assertEqual(self.driver.stage(f.stage)['code'],'STAGING_READY');self.enqueue.assert_not_called()
    def test_failed_stage_does_not_read_or_enqueue_acceptance(self):
        self.stage.return_value={'code':'STAGING_FAILED'}
        self.assertEqual(self.driver.stage(self.f.stage)['code'],'STAGING_FAILED');self.enqueue.assert_not_called()
    def test_verified_bundle_must_match_staged_process_binding(self):
        self.driver.stage(self.f.stage);self.verify.return_value={'server':'wrong','runtime':'wrong'}
        with self.assertRaisesRegex(Exception,'ENQUEUE_RUNTIME_BINDING_CHANGED'):
            self.enqueue.call_args.kwargs['authorize'](self.f.plan)

if __name__=='__main__':unittest.main()
