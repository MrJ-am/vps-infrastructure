import sys,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'ci/continuous-delivery-v1'))
import test_admission_orchestrator
import test_host_views as F
import host_builder as H

class Builder(unittest.TestCase):
    def setUp(self):
        self.f=F.Views();self.f.setUp();self.p=lambda n:'/nix/store/'+'a'*32+'-'+n
        self.f.state.update(schema_version=1,active_slot='blue',slots={s:{k:self.p(s+k) for k in ('server','runtime')} for s in ('blue','green')})
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.work=Path(self.temp.name)
        self.calls=[];self.bad_view=False;self.bad_build=False;self.moved=False
        original=Path.read_bytes
        def read(path):
            if str(path)==self.f.path+'/descriptor.json':return json.dumps(self.f.candidate).encode()
            return original(path)
        p=patch.object(Path,'read_bytes',read);p.start();self.addCleanup(p.stop)
        self.layout=Mock(return_value={'built_layout_verified':True})
    def execute(self,args):
        self.calls.append(args);attr=args[args.index('-A')+1]
        if attr.startswith('views.'):
            v=self.f.views[attr.split('.')[1]];v['input_state_sha256']=H.B.O.sha((self.work/'input-state.json').read_bytes())
            if self.bad_view and v['phase']=='candidate':v['preflight']='f'*64
            return json.dumps(v).encode()
        self.moved=True
        return ((self.p('bad') if self.bad_build else self.f.views['candidate']['system'])+'\n').encode()
    def run_build(self,observe=None):
        return H.Builder('/installed/generations.nix',self.p('nix')+'/bin/nix-instantiate',self.p('nix')+'/bin/nix-build',
            execute=self.execute,layout=self.layout).construct(self.work,self.f.state,self.f.path,
                observe=observe or (lambda:self.f.state['system']))
    def test_two_views_then_build_and_layout(self):
        proof=self.run_build();self.assertTrue(proof['built']);self.assertFalse(proof['deployment_authorized'])
        self.assertEqual([c[c.index('-A')+1] for c in self.calls],['views.current','views.candidate','build'])
        self.layout.assert_called_once();self.assertTrue((self.work/'prepared.json').exists())
    def test_invalid_view_prevents_build(self):
        self.bad_view=True
        with self.assertRaises(ValueError):self.run_build()
        self.assertEqual(len(self.calls),2);self.layout.assert_not_called()
    def test_wrong_built_generation_refused(self):
        self.bad_build=True
        with self.assertRaisesRegex(Exception,'VISE_GENERATION_BUILD_CHANGED'):self.run_build()
        self.layout.assert_not_called();self.assertFalse((self.work/'prepared.json').exists())
    def test_live_change_prevents_receipt(self):
        with self.assertRaisesRegex(Exception,'VISE_GENERATION_LIVE_BASE_CHANGED'):
            self.run_build(lambda:self.p('moved') if self.moved else self.f.state['system'])
        self.assertFalse((self.work/'prepared.json').exists())
    def test_layout_refusal_prevents_receipt(self):
        self.layout.side_effect=ValueError('unsafe')
        with self.assertRaises(ValueError):self.run_build()
        self.assertFalse((self.work/'prepared.json').exists())

if __name__=='__main__':unittest.main()
