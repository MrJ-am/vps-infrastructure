import unittest
from unittest.mock import Mock,patch
import test_accepted_plan as F
import enqueue as E

class PowerLoss(BaseException):pass

class Publish(unittest.TestCase):
    def setUp(self):
        self.f=F.Accepted();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.plan=self.f.compose();self.root=self.f.f.work
        self.state=self.root/'promotion';self.state.mkdir(mode=0o700)
        self.jobs=self.root/'jobs';self.jobs.mkdir(mode=0o700);self.roots=self.root/'roots'
        self.acceptance=self.root/'acceptance';self.acceptance.mkdir(mode=0o700)
        self.events=[]
        for obj,name,value in [(E.P,'load',Mock(side_effect=lambda *a:self.plan)),
                (E.L,'verify',Mock(side_effect=lambda *a,**kw:self.events.append('layout'))),
                (E.V,'verify',Mock(side_effect=lambda *a,**kw:self.events.append('authority')))]:
            p=patch.object(obj,name,value);p.start();self.addCleanup(p.stop)
        self.environment=Mock(side_effect=lambda:self.plan['environment'])
    def publish(self):
        return E.publish(self.state,self.roots,self.jobs,self.acceptance,self.plan['job'],'synthetic-reader',
            environment=self.environment,observe=lambda:(self.plan['old'],)*2)
    def test_shared_queue_gets_exact_plan_after_checks(self):
        self.assertEqual(self.publish()['code'],'PROMOTION_PLAN_ENQUEUED')
        self.assertEqual(self.events,['layout','authority','layout'])
        self.assertEqual(E.N.L.read(self.state/'plan.json'),self.plan)
        key=E.N.R.identity(self.plan)['plan_sha256']
        self.assertEqual(str((self.roots/(key+'-old')).readlink()),self.plan['old'])
        self.assertEqual(str((self.roots/(key+'-new')).readlink()),self.plan['new'])
    def test_failed_authority_never_publishes(self):
        E.V.verify.side_effect=ValueError('expired')
        with self.assertRaisesRegex(ValueError,'expired'):self.publish()
        self.assertFalse((self.state/'plan.json').exists());self.assertFalse(self.roots.exists())
    def test_changed_acceptance_after_authorization_refused(self):
        E.P.load.side_effect=[self.plan,self.plan,{**self.plan,'forge_pull':99}]
        with self.assertRaisesRegex(Exception,'VISE_ENQUEUE_ACCEPTANCE_CHANGED'):self.publish()
        self.assertFalse((self.state/'plan.json').exists())
    def test_environment_change_after_authorization_refused(self):
        self.environment.side_effect=[self.plan['environment'],{}]
        with self.assertRaisesRegex(Exception,'VISE_ENQUEUE_ENVIRONMENT_CHANGED'):self.publish()
        self.assertFalse((self.state/'plan.json').exists())
    def test_built_layout_drift_refused(self):
        E.L.verify.side_effect=ValueError('changed layout')
        with self.assertRaisesRegex(ValueError,'changed layout'):self.publish()
        E.V.verify.assert_not_called()
    def test_pending_other_plan_cannot_be_overwritten(self):
        other={**self.plan,'job':'e'*64};E.O.save(self.state/'plan.json',other)
        with self.assertRaises(Exception):self.publish()
        self.assertEqual(E.N.L.read(self.state/'plan.json'),other)
    def test_lost_write_ack_reuses_same_plan_and_roots(self):
        save=E.O.save
        def interrupted(path,value):save(path,value);raise PowerLoss()
        with patch.object(E.O,'save',side_effect=interrupted):
            with self.assertRaises(PowerLoss):self.publish()
        self.assertEqual(self.publish()['code'],'PROMOTION_PLAN_PRESENT')
        self.assertEqual(len(list(self.roots.iterdir())),2)
    def test_recovery_journal_is_not_reset(self):
        self.publish();key=E.N.R.identity(self.plan)['plan_sha256']
        journal={'schema_version':1,'plan_sha256':key,'phase':'recovering'}
        E.O.save(self.state/(key+'.json'),journal)
        with self.assertRaisesRegex(Exception,'ENQUEUE_PROMOTION_REQUIRES_RECOVERY'):self.publish()
        self.assertEqual(E.N.L.read(self.state/(key+'.json')),journal)

if __name__=='__main__':unittest.main()
