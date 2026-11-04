"""Fixed-head source audit and independently selected synthetic rule tests.

Run only in the Nix builder sandbox. No network, credentials, Forgejo writes,
attestation signing, or deployment are part of this program.
"""
import hashlib,importlib.util,json,os,shutil,stat,sys,unittest
from pathlib import Path

source,binding_file,contract_tests,source_tests,shared,report=map(Path,sys.argv[1:])
interfaces=sorted(line.split(':',1)[0].strip() for line in Path('/proc/net/dev').read_text().splitlines() if ':' in line)
hidden=all(not Path(p).exists() for p in ('/home/jam','/var/lib/forgejo','/run/postgresql'))
assert os.geteuid()!=0 and hidden and interfaces==['lo'], 'AUDIT_SANDBOX_REFUSED'
binding_raw=binding_file.read_bytes();binding=json.loads(binding_raw)
assert binding['head']=='470211d7b2522322a94c5ddfc6770d833bb1457e'
assert binding['base']=='b02bdf1b5d63dcf0e0610723788a7ca7e384932c'
assert binding['tree']=='5d2754e2fa062f4476d36eecc4cd3a2c359a48b1'
actual=set()
for path in source.rglob('*'):
    mode=path.lstat().st_mode
    assert stat.S_ISDIR(mode) or stat.S_ISREG(mode)
    if stat.S_ISREG(mode):actual.add(path.relative_to(source).as_posix())
assert actual==set(binding['files'])|{'export.json'} and len(binding['files'])==21
for name,digest in binding['files'].items():
    assert hashlib.sha256((source/name).read_bytes()).hexdigest()==digest
export=json.loads((source/'export.json').read_bytes())
assert export=={'schema_version':1,'repository':'MrJ-am/mrjam-validation',
    **{name:binding[name] for name in ('head','base','tree')}}

sys.path[:0]=[str(source/'vise-v1/delivery'),str(shared)]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module
    spec.loader.exec_module(module);return module

contracts=load('fixed_contract_tests',contract_tests)
git_tests=load('fixed_git_source_tests',source_tests)

class LargeTree(unittest.TestCase):
    def test_more_than_128_files_survive_complete_git_preparation(self):
        fixture=git_tests.Policy('test_complete_real_git_tree_and_selected_bytes_pass')
        self.addCleanup(fixture.doCleanups);fixture.setUp()
        names=[f'backend/src/module_{n}.rs' for n in range(137)]
        for name in names:fixture.change(name,b'fn synthetic() {}\n')
        head=fixture.commit(fixture.base)
        reader=git_tests.S.NativeObjects(fixture.repo,shutil.which('git'))
        output=fixture.root/'large-prepared'
        result=git_tests.Q.prepare(fixture.input,fixture.digest,fixture.policy,
            {'vise':{'reader':reader,'base':fixture.base,'head':head}},output,
            validator_policy=git_tests.P,gate=git_tests.G,gate_path=git_tests.GATE)
        for name in names:self.assertEqual((output/'sources/vise'/name).read_bytes(),b'fn synthetic() {}\n')
        self.assertEqual(git_tests.P.verify_sources(output,result['policy'],git_tests.GATE)[1],result['proposal_sha256'])

suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromModule(m) for m in (contracts,git_tests))
suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(LargeTree))
assert suite.countTestCases()==19
result=unittest.TextTestRunner(verbosity=2).run(suite)
assert result.wasSuccessful() and result.testsRun==19 and not result.skipped
record={'schema_version':1,'repository':'MrJ-am/mrjam-validation',
    **{name:binding[name] for name in ('head','base','tree')},
    'scope':'independent synthetic rule-contract and real-Git source-binding tests',
    'binding_sha256':hashlib.sha256(binding_raw).hexdigest(),
    'suite_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__),contract_tests,source_tests)},
    'shared_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(shared.glob('*.py'))},
    'tree_gate_sha256':hashlib.sha256(git_tests.GATE.read_bytes()).hexdigest(),
    'tools':{'python':sys.executable,'git':shutil.which('git')},
    'isolation':{'unprivileged':True,'private_host_paths_absent':True,'network_interfaces':interfaces},
    'status':'passed','tests':19,'skipped':0,'proposal_files_verified':21,
    'forgejo_actions_run_id':None,'commit_status_published':False,
    'adoption_authorized':False,'deployment_authorized':False}
report.write_text(json.dumps(record,sort_keys=True,indent=2)+'\n')
