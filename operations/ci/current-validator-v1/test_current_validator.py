"""Targeted actual-byte checks; no application validation result fabricated."""
import copy,hashlib,importlib,json,shutil,stat,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[3]
LOCAL=ROOT/'.local/ci-current-validator-v1-20261103'
PACKAGE=Path((LOCAL/'package-003.stdout').read_text().strip())
SOURCE=Path((LOCAL/'staging-001.stdout').read_text().strip())
BASE=Path('/nix/store/p2494a4mh5nsp77sfzrfd8zhinz34bmp-mrjam-validate')
OLD_RUNTIME=Path('/nix/store/0py92lckwf8la1w2pq6d0cgd42xnpywr-mrjam-verifier-runtime.json')
sys.path.insert(0,str(PACKAGE/'lib'))
import policy,readiness,runner
from sandbox import Refused
RUNTIME=json.loads(runner.RUNTIME.read_bytes())
POLICY=json.loads(Path(RUNTIME['policy']).read_bytes())
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

class CurrentValidator(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix='mrjam-public-readiness-proof-')
        self.directory=Path(self.temporary.name)/'source';self.directory.mkdir()
        for entry in readiness.CONTRACT['files']:
            target=self.directory/entry['path'];target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(SOURCE/'sources/platform'/entry['path'],target)
        (self.directory/'unchanged').write_bytes(b'INVENTED UNRELATED FILE\n')
    def tearDown(self):self.temporary.cleanup()
    def test_exact_public_git_and_manifest_bindings(self):
        target=Path(self.temporary.name)/'complete-public-input';shutil.copytree(SOURCE,target)
        value=policy.checked_policy(copy.deepcopy(POLICY))
        sources,proposal=policy.verify_sources(target,value,Path(RUNTIME['tree_gate']))
        self.assertEqual(len(sources),9)
        self.assertEqual(proposal,json.loads((LOCAL/'proposal-sha256.json').read_bytes()))
        self.assertEqual(value['rules_revision'],'b02bdf1b5d63dcf0e0610723788a7ca7e384932c')
        self.assertEqual(len(json.loads((target/'manifest.json').read_bytes())['files']),815)
    def test_exact_overlay_preserves_unrelated_content(self):
        original=(self.directory/'unchanged').read_bytes()
        self.assertEqual(readiness.apply(self.directory,POLICY),'rust-reviewed-readiness-overlay')
        for entry in readiness.CONTRACT['files']:self.assertEqual(digest(self.directory/entry['path']),entry['compiled_sha256'])
        self.assertEqual((self.directory/'unchanged').read_bytes(),original)
    def test_old_missing_unknown_or_altered_policy_refused(self):
        cases=[]
        old=copy.deepcopy(POLICY);old['schema_version']=1;old.pop('readiness_overlay');cases.append(old)
        for key,value in [('schema_version',True),('schema_version',1),('unexpected',True)]:
            item=copy.deepcopy(POLICY);item[key]=value;cases.append(item)
        for key in ('revision','patch_sha256','base_platform_revision'):
            item=copy.deepcopy(POLICY);item['readiness_overlay'][key]='0'*len(item['readiness_overlay'][key]);cases.append(item)
        item=copy.deepcopy(POLICY);item['readiness_overlay']['unexpected']='forbidden';cases.append(item)
        for item in cases:
            with self.subTest(item=item.keys()),self.assertRaises(Refused):policy.checked_policy(item)
    def test_other_platform_revision_refused(self):
        item=copy.deepcopy(POLICY)
        next(x for x in item['sources'] if x['id']=='platform')['revision']='0'*40
        with self.assertRaisesRegex(Refused,'READINESS_BASE_REVISION_REFUSED'):policy.checked_policy(item)
    def test_mutated_base_refused_before_changes(self):
        target=self.directory/readiness.CONTRACT['files'][0]['path'];target.write_bytes(target.read_bytes()+b'\n')
        before=readiness.inventory(self.directory)
        with self.assertRaisesRegex(Refused,'READINESS_BASE_CONTENT_REFUSED'):readiness.apply(self.directory,POLICY)
        self.assertEqual(readiness.inventory(self.directory),before)
    def test_mutated_patch_refused_before_changes(self):
        malformed=Path(self.temporary.name)/'modified.patch';malformed.write_bytes(readiness.PATCH.read_bytes()+b'\n')
        before=readiness.inventory(self.directory)
        with patch.object(readiness,'PATCH',malformed),self.assertRaisesRegex(Refused,'READINESS_PATCH_HASH_REFUSED'):readiness.apply(self.directory,POLICY)
        self.assertEqual(readiness.inventory(self.directory),before)
    def test_unexpected_postimage_refused(self):
        contract=copy.deepcopy(readiness.CONTRACT);contract['files'][0]['compiled_sha256']='0'*64
        item=copy.deepcopy(POLICY);item['readiness_overlay']=contract
        with patch.object(readiness,'CONTRACT',contract),self.assertRaisesRegex(Refused,'READINESS_COMPILED_CONTENT_REFUSED'):readiness.apply(self.directory,item)
    def test_unrelated_tool_write_refused(self):
        actual=subprocess.run
        def changed(*args,**kwargs):
            result=actual(*args,**kwargs);(self.directory/'unchanged').write_bytes(b'UNEXPECTED TOOL CHANGE\n');return result
        with patch.object(readiness.subprocess,'run',changed),self.assertRaisesRegex(Refused,'READINESS_COMPILED_CONTENT_REFUSED'):readiness.apply(self.directory,POLICY)
    def test_source_link_refused(self):
        (self.directory/'unexpected-link').symlink_to('/etc/passwd')
        with self.assertRaisesRegex(Refused,'READINESS_SOURCE_TYPE_REFUSED'):readiness.apply(self.directory,POLICY)
    def test_actual_rust_method_applies_overlay_before_cargo(self):
        class ReachedFirstCargo(Exception):pass
        instance=object.__new__(runner.Verifier);instance.private=Path(self.temporary.name)/'private';instance.private.mkdir()
        instance.policy=POLICY;instance.steps=[];instance.runtime=RUNTIME;instance.tools=RUNTIME['tools']
        instance.source=lambda identifier:SOURCE/'sources'/identifier
        instance.job=lambda name:runner.new_directory(Path(self.temporary.name)/name)
        def check(name,source,job,argv,**kwargs):
            self.assertEqual(name,'rust-format')
            self.assertEqual(instance.steps,[{'name':'rust-reviewed-readiness-overlay','status':'passed'}])
            for entry in readiness.CONTRACT['files']:self.assertEqual(digest(source/entry['path']),entry['compiled_sha256'])
            raise ReachedFirstCargo()
        instance.check=check
        with self.assertRaises(ReachedFirstCargo):instance.rust()
    def test_packaged_control_diff_and_pinned_runtime(self):
        self.assertEqual((PACKAGE/'lib/base_policy.py').read_bytes(),(BASE/'lib/policy.py').read_bytes())
        expected=(BASE/'lib/runner.py').read_text().replace(str(OLD_RUNTIME),str(runner.RUNTIME))
        expected=expected.replace('import policy as rules','import policy as rules\nimport readiness')
        expected=expected.replace('        # No candidate Cargo configuration can redirect a compiler, registry,','        self.steps.append({"name": readiness.apply(source, self.policy), "status": "passed"})\n        # No candidate Cargo configuration can redirect a compiler, registry,')
        expected=expected.replace('"elm-entrypoint-" + name + "-" + Path(target).stem','"elm-entrypoint-" + name + "-" + Path(target).stem.lower()')
        self.assertEqual((PACKAGE/'lib/runner.py').read_text(),expected)
        for path in (BASE/'lib').iterdir():
            if path.name not in ('runner.py','policy.py'):self.assertEqual((PACKAGE/'lib'/path.name).read_bytes(),path.read_bytes())
        old=json.loads(OLD_RUNTIME.read_bytes());self.assertEqual({k:v for k,v in RUNTIME.items() if k!='policy'},{k:v for k,v in old.items() if k!='policy'})
        self.assertNotEqual(RUNTIME['policy'],old['policy'])
    def test_invalid_packaged_invocation_remains_closed(self):
        result=subprocess.run([str(PACKAGE/'bin/mrjam-validate'),'/arbitrary'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5,check=False)
        self.assertEqual((result.returncode,result.stdout),(1,b''));self.assertEqual(json.loads(result.stderr),{'decision':'failed','code':'INVALID_INVOCATION'})

if __name__=='__main__':unittest.main(verbosity=2)
