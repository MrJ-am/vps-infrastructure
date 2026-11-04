import json,tempfile,unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch
import test_admission_orchestrator
import test_generation_views as V
import generation_builder as B

class Builder(unittest.TestCase):
    def setUp(self):
        self.fixture=V.Views();self.fixture.setUp();self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.work=Path(self.tmp.name);self.calls=[];self.change=False;self.bad_build=False;self.invalid_view=False
        self.candidate=self.fixture.p('candidate');self.base=self.fixture.state['system']
        self.real_read=Path.read_bytes
        def read(path):
            if str(path)==self.candidate+'/descriptor.json':return json.dumps(self.fixture.candidate).encode()
            if str(path)==self.fixture.candidate['bundle']+'/descriptor.json':return json.dumps(self.fixture.bundle).encode()
            return self.real_read(path)
        p=patch.object(Path,'read_bytes',read);p.start();self.addCleanup(p.stop)
    def execute(self,args):
        self.calls.append(args);attr=args[args.index('-A')+1];phase=attr.split('.')[1]
        if attr.startswith('views.'):
            view=self.fixture.views[phase]
            view['input_state_sha256']=B.O.sha((self.work/'input-state.json').read_bytes())
            if self.invalid_view and phase=='promotion':view['slot_services']['green']='f'*64
            return json.dumps(view).encode()
        self.change=True
        if self.bad_build:return (self.fixture.p('wrong-system')+'\n').encode()
        return (self.fixture.views[phase]['state']['system']+'\n').encode()
    def builder(self):return B.Builder('/installed/delivery-generations.nix',self.fixture.p('nix')+'/bin/nix-instantiate',self.fixture.p('nix')+'/bin/nix-build',self.execute)
    def run_build(self,observe=None):return self.builder().construct(self.work,self.fixture.state,self.candidate,observe=observe or (lambda:self.base))
    def test_three_views_then_two_builds_and_bound_receipt(self):
        proof=self.run_build();self.assertEqual(len(self.calls),5);self.assertTrue(proof['built'])
        self.assertFalse(proof['deployment_authorized']);self.assertTrue((self.work/'prepared.json').exists())
        self.assertEqual([c[c.index('-A')+1] for c in self.calls],['views.current','views.stage','views.promotion','builds.stage','builds.promotion'])
        for call in self.calls[:3]:self.assertIn('--read-write-mode',call)
    def test_invalid_view_never_reaches_build(self):
        self.invalid_view=True
        with self.assertRaisesRegex(Exception,'GENERATION_INVARIANT_REFUSED'):self.run_build()
        self.assertEqual(len(self.calls),3);self.assertFalse((self.work/'prepared.json').exists())
    def test_changed_build_result_never_reaches_next_build(self):
        self.bad_build=True
        with self.assertRaisesRegex(Exception,'GENERATION_BUILD_RESULT_CHANGED'):self.run_build()
        self.assertEqual(len(self.calls),4);self.assertFalse((self.work/'prepared.json').exists())
    def test_changed_live_base_cannot_get_prepared_receipt(self):
        with self.assertRaisesRegex(Exception,'GENERATION_LIVE_BASE_CHANGED'):
            self.run_build(lambda:self.fixture.p('moved') if self.change else self.base)
        self.assertFalse((self.work/'prepared.json').exists())
    def test_wrong_base_prevents_all_commands(self):
        with self.assertRaisesRegex(Exception,'GENERATION_LIVE_BASE_CHANGED'):self.run_build(lambda:self.fixture.p('moved'))
        self.assertEqual(self.calls,[])
    def test_prepared_work_cannot_be_rebound_to_another_candidate(self):
        self.run_build();self.calls.clear();self.candidate=self.fixture.p('other-candidate')
        with self.assertRaisesRegex(Exception,'GENERATION_INPUTS_CHANGED'):self.run_build()
        self.assertEqual(self.calls,[])
    def test_command_uses_daemon_inside_read_only_service(self):
        with patch.object(B.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout=b'output',stderr=b'')) as run:
            self.assertEqual(B.Builder.command(['/fixed/nix']),b'output')
            self.assertEqual(run.call_args.kwargs['env']['NIX_REMOTE'],'daemon')
    def test_error_exports_only_closed_code(self):
        for text,code in [(b'Read-only file system: private details','GENERATION_STORE_READ_ONLY'),
                (b'Permission denied: private details','GENERATION_STORE_PERMISSION_REFUSED'),
                (b'other private details','GENERATION_COMMAND_REFUSED')]:
            with patch.object(B.subprocess,'run',return_value=SimpleNamespace(returncode=1,stdout=b'',stderr=text)):
                with self.assertRaisesRegex(Exception,'^'+code+'$'):B.Builder.command(['/fixed/nix'])

if __name__=='__main__':unittest.main()
