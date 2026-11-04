import sys,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'authority-v1'))
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'forgejo'))
import test_admission_orchestrator
import staging_adapter as A

class RuntimeChecks(unittest.TestCase):
    def setUp(self):
        self.a=A.Adapter.__new__(A.Adapter)
        p=lambda name:'/nix/store/'+'a'*32+'-'+name
        self.state={'system':p('system'),'adopted':p('adopted'),'active_slot':'blue',
            'slots':{s:{'server':p(s+'-server'),'runtime':p(s+'-runtime')} for s in ('blue','green')}}
        self.a.targets={'new':self.state};self.a.slot='green';self.a.routes=b'fixed routes'
        self.a.before={'public':'unchanged'};self.a.retained=Mock(return_value=self.a.before)
        self.a.phase=Mock(return_value='boot');self.a.checkpoint=Mock()
        self.current=self.profile=self.state['system'];self.dropin=False;self.routes=self.a.routes
        patches=[patch.object(A,'actual',side_effect=lambda:(self.current,self.profile)),
            patch.object(A.os.path,'realpath',return_value=self.state['adopted']),
            patch.object(A.Path,'read_bytes',side_effect=lambda:self.routes),
            patch.object(A.Path,'exists',side_effect=lambda:self.dropin),
            patch.object(A.Path,'iterdir',return_value=iter([Path('/synthetic/dropin')])),
            patch.object(A.R,'capture',return_value={'synthetic':'new-process-proof'}),patch.object(A,'run')]
        self.mocks=[]
        for p in patches:self.mocks.append(p.start());self.addCleanup(p.stop)
        self.capture=self.mocks[-2];self.run=self.mocks[-1]
    def test_ready_after_reboot_refreshes_proof_without_activation(self):
        self.a.phase.return_value='ready';self.a.verify('new',boot=True)
        self.a.checkpoint.assert_called_once_with('ready');self.run.assert_not_called()
        self.assertEqual(self.a.runtime,{'synthetic':'new-process-proof'})
    def test_wrong_boot_prevents_readiness_and_proof_publication(self):
        self.profile='/other'
        with self.assertRaisesRegex(Exception,'STAGING_GENERATION_REFUSED'):self.a.verify('new',boot=True)
        self.capture.assert_not_called();self.a.checkpoint.assert_not_called();self.run.assert_not_called()
    def test_changed_public_process_refused_before_probe(self):
        self.a.retained.return_value={'public':'restarted'}
        with self.assertRaisesRegex(Exception,'STAGING_PUBLIC_PROCESS_CHANGED'):self.a.verify('new',boot=True)
        self.capture.assert_not_called()
    def test_public_process_change_during_readiness_wait_refused(self):
        self.a.retained.side_effect=[self.a.before,{'public':'restarted'}]
        with self.assertRaisesRegex(Exception,'STAGING_PUBLIC_PROCESS_CHANGED'):self.a.verify('new',boot=True)
        self.capture.assert_called_once();self.a.checkpoint.assert_not_called()
    def test_unexpected_dropin_prevents_execution_claim(self):
        self.dropin=True
        with self.assertRaisesRegex(Exception,'STAGING_DROPIN_REFUSED'):self.a.verify('new',boot=True)
        self.capture.assert_not_called()
    def test_changed_public_route_refused(self):
        self.routes=b'wrong routes'
        with self.assertRaisesRegex(Exception,'STAGING_PUBLIC_ROUTE_CHANGED'):self.a.verify('new',boot=True)
        self.capture.assert_not_called()

if __name__=='__main__':unittest.main()
