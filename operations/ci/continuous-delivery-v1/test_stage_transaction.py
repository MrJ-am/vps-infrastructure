import unittest
import stage_transaction as S

class Adapter:
    old='old';new='new'
    def __init__(self):self.current='old';self.phases=[];self.stops=0;self.fail=False;self.clients=False;self.started=True
    def preflight(self):
        if self.clients:raise RuntimeError('clients')
    def retained(self):return 'public-green-process'
    def checkpoint(self,phase):self.phases.append(phase)
    def no_clients(self):
        if self.clients:raise RuntimeError('clients')
    def stop_slot(self):self.started=False;self.stops+=1
    def switch(self,target):self.current=target
    def start_slot(self):self.started=True
    def verify(self,target,before):
        assert before=='public-green-process' and self.current==target and self.started
        if self.fail and target=='new':raise RuntimeError('candidate not ready')

class Stage(unittest.TestCase):
    def test_success_exercises_return_before_final_stage(self):
        a=Adapter();result=S.stage(a)
        self.assertTrue(result['real_return_verified']);self.assertFalse(result['routes_changed'])
        self.assertEqual(a.phases,['prepared','first-stage','real-return','final-stage','off-traffic-ready-return-verified'])
        self.assertEqual(a.current,'new');self.assertEqual(a.stops,3)
    def test_candidate_readiness_failure_returns_old_and_restarts_it(self):
        a=Adapter();a.fail=True;result=S.stage(a)
        self.assertTrue(result['previous_restored']);self.assertEqual(a.current,'old');self.assertTrue(a.started)
    def test_existing_clients_prevent_every_mutation(self):
        a=Adapter();a.clients=True
        with self.assertRaises(RuntimeError):S.stage(a)
        self.assertEqual(a.stops,0);self.assertEqual(a.phases,[])
    def test_return_failure_not_reported_as_success(self):
        a=Adapter()
        def broken(target,before):raise RuntimeError('unavailable')
        a.verify=broken;result=S.stage(a)
        self.assertFalse(result['previous_restored']);self.assertEqual(a.phases[-1],'recovery-required')

if __name__=='__main__':unittest.main()
