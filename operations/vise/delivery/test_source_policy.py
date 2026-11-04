import copy,hashlib,importlib.util,json,os,shutil,subprocess,sys,tempfile,unittest
from pathlib import Path
import source_policy as P

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[1]/'ci/continuous-delivery-v1'))
import source_snapshot as S,proposal_prepare as Q,proposal_policy as V
GATE=Path('/nix/store/26qr08ambmn7g5dccqbr8q7aqkvcd92f-check_git_tree.py')
spec=importlib.util.spec_from_file_location('vise_test_gate',GATE)
G=importlib.util.module_from_spec(spec);spec.loader.exec_module(G)

class Policy(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.root.chmod(0o700)
        self.repo=self.root/'objects.git';self.repo.mkdir(mode=0o700)
        self.env={'PATH':'/nonexistent','HOME':'/nonexistent','GIT_CONFIG_NOSYSTEM':'1',
            'GIT_CONFIG_GLOBAL':'/dev/null','GIT_INDEX_FILE':str(self.root/'index'),
            'GIT_AUTHOR_NAME':'Fixture','GIT_AUTHOR_EMAIL':'fixture@example.invalid',
            'GIT_COMMITTER_NAME':'Fixture','GIT_COMMITTER_EMAIL':'fixture@example.invalid'}
        self.git('init','--bare','--quiet',str(self.repo))
        self.files={n:(b'{}' if n.endswith('.json') else b'synthetic\n') for n in P.S.EXACT}
        self.files.update({'backend/src/main.rs':b'fn main() {}\n',
            'frontend/src/Main.elm':b'module Main exposing (main)\n',
            'bridge/new.ts':b'export const fixture = true;\n',
            'tests/api.test.ts':b'// synthetic\n','scripts/build.mjs':b'// synthetic\n',
            'README.org':b'Unselected synthetic prose\n'})
        for name,raw in self.files.items():self.change(name,raw)
        self.base=self.commit();reader=S.NativeObjects(self.repo,shutil.which('git'))
        tree=S.complete_tree(reader,self.base)
        self.source={'id':'vise','repository':'MrJ-am/etp-vie-affective','revision':self.base,
            'tree_sha':tree['sha'],'root':P.ROOT,'tree_json':P.TREE}
        self.policy={'schema_version':2,'status':'proposed-not-independently-adopted','profile':'vise-v1',
            'rules_revision':'a'*40,'sources':[self.source],'frontends':[],
            'rust_manifests':{'components/vise/'+n:hashlib.sha256(self.files[n]).hexdigest()
                for n in ['backend/Cargo.toml','backend/Cargo.lock']},'out_of_scope':P.OUT_OF_SCOPE.copy()}
        self.input=self.root/'input';self.input.mkdir(mode=0o700)
        for name,raw in self.files.items():
            if P.S.selected(name) or G.active_configuration(name):self.put(P.ROOT+'/'+name,raw)
        self.put(P.TREE,Q.encode(tree))
        self.put('source-bindings.json',Q.encode({'schema_version':1,'rules_revision':'a'*40,
            'sources':[{k:self.source[k] for k in ['id','repository','revision','tree_sha']}]}))
        self.manifest()
    def git(self,*args,raw=None):
        return subprocess.check_output([shutil.which('git'),'-c','core.hooksPath=/dev/null',
            '--git-dir='+str(self.repo),*args],env=self.env,input=raw,stderr=subprocess.DEVNULL).strip().decode()
    def change(self,name,raw):
        oid=self.git('hash-object','-w','--stdin',raw=raw)
        self.git('update-index','--add','--cacheinfo','100644,'+oid+','+name)
    def commit(self,parent=None):
        args=['commit-tree',self.git('write-tree'),'-m','Synthetic source only']
        if parent:args+=['-p',parent]
        return self.git(*args)
    def put(self,name,raw):
        p=self.input/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
    def manifest(self):
        rows=[]
        for p in sorted(self.input.rglob('*')):
            if p.is_file() and p.name!='manifest.json':
                raw=p.read_bytes();rows.append({'path':str(p.relative_to(self.input)),
                    'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
        self.put('manifest.json',Q.encode({'schema_version':1,'rules_revision':'a'*40,'files':rows}))
        self.digest=P.sha(self.input/'manifest.json')
    def verify(self):return P.verify_sources(self.input,self.policy,GATE)
    def test_complete_real_git_tree_and_selected_bytes_pass(self):
        self.assertEqual(self.verify(),({'vise':self.source},self.digest))
    def test_changed_bytes_with_forged_manifest_still_fail_git_binding(self):
        self.put(P.ROOT+'/bridge/new.ts',b'forged');self.manifest()
        with self.assertRaisesRegex(P.Refused,'BLOB_MISMATCH'):self.verify()
    def test_omitted_selected_code_cannot_be_hidden_by_updating_manifest(self):
        (self.input/P.ROOT/'bridge/new.ts').unlink();self.manifest()
        with self.assertRaisesRegex(P.Refused,'SCOPE_INCOMPLETE'):self.verify()
    def test_unselected_input_is_rejected_even_when_declared(self):
        self.put(P.ROOT+'/README.org',self.files['README.org']);self.manifest()
        with self.assertRaisesRegex(P.Refused,'SCOPE_INCOMPLETE'):self.verify()
    def test_symlink_parent_is_refused_before_descendant_reads(self):
        d=self.input/P.ROOT/'bridge';shutil.rmtree(d)
        d.symlink_to(self.root,target_is_directory=True)
        with self.assertRaisesRegex(P.Refused,'DIRECTORY_REFUSED'):self.verify()
    def test_wrong_project_or_rules_cannot_reuse_this_policy(self):
        self.policy['sources'][0]['repository']='MrJ-am/mrjam-plateforme'
        with self.assertRaisesRegex(P.Refused,'IDENTITY_REFUSED'):self.verify()
    def test_real_proposal_preparer_and_independent_consumer_use_vise_scope(self):
        self.change('bridge/added.ts',b'export const added = true;\n')
        self.change('backend/build.rs',b'fn main() {}\n');head=self.commit(self.base)
        reader=S.NativeObjects(self.repo,shutil.which('git'))
        result=Q.prepare(self.input,self.digest,self.policy,{'vise':{'reader':reader,'base':self.base,'head':head}},
            self.root/'prepared',validator_policy=P,gate=G,gate_path=GATE)
        self.assertEqual((self.root/'prepared'/P.ROOT/'bridge/added.ts').read_bytes(),b'export const added = true;\n')
        self.assertEqual((self.root/'prepared'/P.ROOT/'backend/build.rs').read_bytes(),b'fn main() {}\n')
        source=result['policy']['sources'][0]
        observed={'vise':{k:source[k] for k in ['repository','revision','tree_sha']}}
        self.assertEqual(V.verify(self.root/'prepared',self.policy,result['policy'],observed,
            result['proposal_sha256'],validator_policy=P,gate_path=GATE),result['policy'])
    def test_new_root_workspace_cannot_be_silently_omitted(self):
        self.change('Cargo.toml',b'[workspace]\nmembers=["backend"]\n');head=self.commit(self.base)
        with self.assertRaisesRegex(P.Refused,'VISE_RUST_GRAPH_CHANGED'):
            Q.prepare(self.input,self.digest,self.policy,{'vise':{
                'reader':S.NativeObjects(self.repo,shutil.which('git')),'base':self.base,'head':head}},
                self.root/'prepared',validator_policy=P,gate=G,gate_path=GATE)
        self.assertFalse((self.root/'prepared').exists())

if __name__=='__main__':unittest.main()
