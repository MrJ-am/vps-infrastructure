"""Real Git objects, fixed accepted code, isolated local proposals; no remote IO."""
import importlib.util,json,os,shutil,subprocess,sys,tempfile,unittest
from pathlib import Path
import proposal_prepare as Q
import proposal_policy as V
import copy

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
BASE=Path('/nix/store/hqh3b9b2z13rqbkn4hy73m2vln3apl1r-mrjam-aligned-public-source-proposal-003')
DIGEST='04754e2c5e531c37bd06864ed2becb3fc218d20d780d9a8c8e1b045956a5d04d'
HEAD='5a05461e9e3eb7cf77e99b85ae8d49630f13004d'
sys.path.insert(0,'/nix/store/crhzij9iqk4pya3p9l52n6kraiq3hzg0-mrjam-validate-aligned-workspace-1/lib')
import policy as P
GATE=Path('/nix/store/26qr08ambmn7g5dccqbr8q7aqkvcd92f-check_git_tree.py')
SPEC=importlib.util.spec_from_file_location('tree_gate',GATE);G=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(G)
POLICY=json.loads((HERE/'aligned-policy.json').read_bytes())
GIT=shutil.which('git')

class Preparation(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.repo=self.root/'objects.git';self.repo.mkdir(mode=0o700)
        self.env={'PATH':'/nonexistent','HOME':'/nonexistent','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null',
                  'GIT_NO_REPLACE_OBJECTS':'1','GIT_ALLOW_PROTOCOL':'','GIT_INDEX_FILE':str(self.root/'index')}
        self.git('init','--bare','--quiet',str(self.repo))
        objects=ROOT/'.local/deployment-20261101/private-histories-20261102/bare/mrjam-plateforme.git/objects'
        self.assertTrue(objects.is_dir())
        (self.repo/'objects/info/alternates').write_text(str(objects)+'\n')
        self.git('read-tree',HEAD)
    def git(self,*args,raw=None):
        return subprocess.check_output([GIT,'-c','core.hooksPath=/dev/null','--git-dir='+str(self.repo),*args],env=self.env,input=raw,stderr=subprocess.DEVNULL).strip().decode()
    def change(self,name,raw):
        oid=self.git('hash-object','-w','--stdin',raw=raw)
        self.git('update-index','--add','--cacheinfo','100644,'+oid+','+name)
    def commit(self,message='Synthetic source preparation only',parent=HEAD):
        tree=self.git('write-tree')
        raw=('tree '+tree+'\n'+('parent '+parent+'\n' if parent else '')+'author Synthetic <synthetic@example.invalid> 1793700000 +0000\ncommitter Synthetic <synthetic@example.invalid> 1793700000 +0000\n\n'+message+'\n').encode()
        return self.git('hash-object','-t','commit','-w','--stdin',raw=raw)
    def prepare(self,head=None,**kwargs):
        return Q.prepare(BASE,kwargs.get('digest',DIGEST),POLICY,{'platform':{
            'reader':Q.S.NativeObjects(self.repo,GIT),'base':kwargs.get('base',HEAD),'head':head or self.commit()}},
            kwargs.get('destination',self.root/'prepared'),validator_policy=P,gate=G,gate_path=GATE)
    def test_exact_tree_new_commit_binds_revision(self):
        head=self.commit();result=self.prepare(head)
        self.assertEqual(result['files'],833)
        self.assertEqual(next(s for s in result['policy']['sources'] if s['id']=='platform')['revision'],head)
        self.assertNotEqual(result['proposal_sha256'],DIGEST)
        self.assertFalse(result['deployment_authorized'])
    def test_added_rust_is_received_without_old_path_inventory(self):
        self.change('crates/server/src/new_synthetic.rs',b'// invented added Rust source\n')
        result=self.prepare()
        self.assertEqual(result['files'],834)
        self.assertEqual((self.root/'prepared/sources/platform/crates/server/src/new_synthetic.rs').read_bytes(),b'// invented added Rust source\n')
    def test_bad_base_and_bad_manifest_refused_before_output(self):
        for kwargs in [{'digest':'0'*64},{'base':'0'*40}]:
            with self.assertRaises(Q.S.Refused):self.prepare(**kwargs)
            self.assertFalse((self.root/'prepared').exists())
    def test_same_tree_different_commits_have_different_proposal_digests(self):
        first=self.prepare(self.commit('first'),destination=self.root/'first')
        second=self.prepare(self.commit('second'),destination=self.root/'second')
        self.assertNotEqual(first['proposal_sha256'],second['proposal_sha256'])
        self.assertEqual(first['policy']['sources'][-1]['tree_sha'],second['policy']['sources'][-1]['tree_sha'])
    def test_newer_observed_main_must_descend_from_adopted_revision(self):
        newer=self.commit('newer main');head=self.commit('proposal',parent=newer)
        result=self.prepare(head,base=newer)
        self.assertEqual(next(s for s in result['policy']['sources'] if s['id']=='platform')['revision'],head)
    def test_unrelated_main_is_refused_even_with_same_content(self):
        unrelated=self.commit('unrelated root',parent=None);head=self.commit('proposal',parent=unrelated)
        with self.assertRaisesRegex(Q.S.Refused,'BASE_NOT_ANCESTOR'):self.prepare(head,base=unrelated)
        self.assertFalse((self.root/'prepared').exists())
    def test_existing_destination_is_not_modified(self):
        target=self.root/'prepared';target.mkdir();(target/'retained').write_text('invented')
        with self.assertRaises(FileExistsError):self.prepare()
        self.assertEqual((target/'retained').read_text(),'invented')
    def test_invalid_gitlink_is_refused_and_partial_removed(self):
        self.git('update-index','--cacheinfo','160000,'+HEAD+',components/vision')
        with self.assertRaises(Exception) as caught:self.prepare()
        self.assertEqual(getattr(caught.exception,'code',None),'GITLINK_COMMIT_MISMATCH')
        self.assertFalse((self.root/'prepared').exists())
    def test_workspace_scope_cannot_be_reduced(self):
        self.change('Cargo.toml',b'[workspace]\nmembers = ["crates/server"]\n')
        with self.assertRaisesRegex(P.Refused,'WORKSPACE_SCOPE_CHANGED'):self.prepare()
        self.assertFalse((self.root/'prepared').exists())
    def test_shared_destination_parent_refused(self):
        self.root.chmod(0o755)
        with self.assertRaisesRegex(Q.S.Refused,'DESTINATION_PARENT_REFUSED'):self.prepare()
        self.assertFalse((self.root/'prepared').exists())
    def test_independent_policy_check_binds_fresh_commit_and_tree(self):
        result=self.prepare()
        source=next(s for s in result['policy']['sources'] if s['id']=='platform')
        observed={'platform':{k:source[k] for k in ('repository','revision','tree_sha')}}
        def verify(policy,obs=observed):
            return V.verify(self.root/'prepared',POLICY,policy,obs,result['proposal_sha256'],validator_policy=P,gate_path=GATE)
        self.assertEqual(verify(result['policy']),result['policy'])
        changed=copy.deepcopy(result['policy']);changed['out_of_scope']=[]
        with self.assertRaisesRegex(P.Refused,'UNDECLARED_SCOPE'):verify(changed)
        changed=copy.deepcopy(result['policy']);changed['rust_manifests']['Cargo.toml']='0'*64
        with self.assertRaisesRegex(Q.S.Refused,'INTAKE_POLICY_CHANGED'):verify(changed)
        changed=copy.deepcopy(observed);changed['platform']['revision']='0'*40
        with self.assertRaisesRegex(Q.S.Refused,'INTAKE_POLICY_CHANGED'):verify(result['policy'],changed)
    def test_intake_cannot_change_an_unobserved_source(self):
        result=self.prepare();sources=result['policy']['sources']
        source=next(s for s in sources if s['id']=='platform')
        observed={'platform':{k:source[k] for k in ('repository','revision','tree_sha')}}
        next(s for s in sources if s['id']=='vision')['revision']='0'*40
        with self.assertRaisesRegex(Q.S.Refused,'INTAKE_POLICY_CHANGED'):
            V.verify(self.root/'prepared',POLICY,result['policy'],observed,result['proposal_sha256'],validator_policy=P,gate_path=GATE)

if __name__=='__main__':unittest.main()
