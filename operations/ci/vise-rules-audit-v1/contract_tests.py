"""Operator-selected expectations, outside the rules proposal under test."""
import copy,hashlib,json,os,tarfile,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
import source_scope as S
import source_policy as P
import authority_profile as A
import artifacts as F

# Do not derive mandatory gates, source identity or release authority from the
# proposed modules: those are exactly the claims this suite must challenge.
STEPS=('complete-vise-source-tree','locked-toolchain-versions',
    'locked-cargo-npm-elm-dependencies','rust-offline-release-build',
    'typescript-no-emit','vise-frontend-build','vise-component-tests',
    'vise-api-tests-synthetic-postgresql','vise-schema-and-role-refusals',
    'vise-graceful-stop-and-restart','vise-restore-current-erasure-ledger',
    'vise-artifact-content-bound')
LIMITS=('Independent release acceptance is not established by this content report.',
    'Production deployment is not authorized by this content report.',
    'No production database, erasure ledger or backup was used in validation.')
EXACT={'COPYING','LICENSE','backend/Cargo.toml','backend/Cargo.lock',
    'elm.json','package.json','package-lock.json','tsconfig.json'}

def policy():
    return {'schema_version':2,'status':'proposed-not-independently-adopted','profile':'vise-v1',
        'rules_revision':'a'*40,'sources':[{'id':'vise','repository':'MrJ-am/etp-vie-affective',
            'revision':'b'*40,'tree_sha':'c'*40,'root':'sources/vise','tree_json':'trees/vise.json'}],
        'frontends':[],'rust_manifests':{'components/vise/backend/Cargo.toml':'d'*64,
            'components/vise/backend/Cargo.lock':'e'*64},
        'out_of_scope':['platform: unchanged releases are not requalified by the ViSe pipeline']}

class Contracts(unittest.TestCase):
    def test_mandatory_gates_and_limits_are_fixed_outside_proposal(self):
        self.assertEqual(tuple(A.REQUIRED_STEPS),STEPS)
        self.assertEqual(tuple(A.NOT_ESTABLISHED),LIMITS)
        self.assertEqual(set(S.EXACT),EXACT)
        self.assertEqual(F.LIMITS,(('server',67108864),('frontend.tar',67108864),('verification.json',65536)))

    def test_new_source_categories_are_selected(self):
        names=sorted(EXACT)+[f'backend/src/module_{n}.rs' for n in range(137)]
        names+=['backend/build.rs','backend/tests/extra.rs','backend/migrations/002.sql',
            'bridge/extra.ts','frontend/src/New.elm','shared/elm/New.elm',
            'shared/assets/new.css','scripts/build-new.mjs','tests/new.test.ts','content/new.json']
        for name in names:
            with self.subTest(path=name):self.assertTrue(S.selected(name))

    def test_secrets_outputs_and_escaping_paths_not_selected(self):
        for name in ['.env','backend/src/key.pem','frontend/secret.key','content/users.sqlite',
            'target/release/server','node_modules/a/index.js','dist/index.html','backup/data.dump',
            '../backend/src/main.rs','backend/src/../main.rs','/backend/src/main.rs',
            'backend//main.rs','backend/./main.rs','backend\\main.rs','backend/main.rs\0',None,42]:
            with self.subTest(path=name):self.assertFalse(S.selected(name))

    def test_policy_rejects_widened_or_rebound_authority(self):
        self.assertEqual(P.checked_policy(policy()),policy())
        changes=[('schema_version',True),('profile','platform'),('status','adopted'),
            ('rules_revision','a'*39),('sources',[]),('frontends',['unqualified']),
            ('rust_manifests',{}),('out_of_scope',[]),('production_authorized',True)]
        for key,value in changes:
            changed=policy();changed[key]=value
            with self.subTest(field=key),self.assertRaises(P.Refused):P.checked_policy(changed)
        for key,value in [('id','platform'),('repository','MrJ-am/mrjam-plateforme'),
            ('root','/var/lib/forgejo'),('tree_json','../tree.json'),('revision','b'*39),('extra',True)]:
            changed=policy();changed['sources'][0][key]=value
            with self.subTest(source_field=key),self.assertRaises(P.Refused):P.checked_policy(changed)

    def test_duplicate_json_and_nonregular_inputs_refused(self):
        with self.assertRaises(P.Refused):P.pairs([('schema_version',1),('schema_version',2)])
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source';source.write_bytes(b'synthetic')
            self.assertEqual(P.read(source),b'synthetic')
            link=root/'link';link.symlink_to(source)
            with self.assertRaises((P.Refused,OSError)):P.read(link)
            os.link(source,root/'hardlink')
            with self.assertRaises(P.Refused):P.read(source)
            os.mkfifo(root/'fifo')
            with self.assertRaises(P.Refused):P.read(root/'fifo')

    def test_authority_must_call_contract_and_bind_exact_rules_sources_steps(self):
        value=policy();raw=json.dumps(value).encode()
        authority={'rules_revision':'a'*40,'report_policy_sha256':hashlib.sha256(raw).hexdigest(),
            'sources':[{k:value['sources'][0][k] for k in ('id','repository','revision','tree_sha')}],
            'required_steps':list(STEPS),'not_established':list(LIMITS)}
        calls=[]
        contract=SimpleNamespace(policy=lambda a:calls.append(copy.deepcopy(a)))
        self.assertEqual(A.expected_steps(authority,raw,contract=contract,rules_revision='a'*40),
            [{'name':n,'status':'passed'} for n in STEPS]);self.assertEqual(calls,[authority])
        class Denied(Exception):pass
        def deny(_):raise Denied()
        with self.assertRaises(Denied):
            A.expected_steps(authority,raw,contract=SimpleNamespace(policy=deny),rules_revision='a'*40)
        for key,bad in [('rules_revision','f'*40),('report_policy_sha256','0'*64),
            ('sources',[]),('required_steps',list(STEPS[:-1])),('not_established',[])]:
            changed=copy.deepcopy(authority);changed[key]=bad
            with self.subTest(field=key),self.assertRaises(P.Refused):
                A.expected_steps(changed,raw,contract=contract,rules_revision='a'*40)

class Receipts(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.out=self.root/'output';self.out.mkdir()
        server=self.root/'server';server.write_bytes(b'\x7fELFsynthetic-not-executable')
        dist=self.root/'dist';dist.mkdir();(dist/'index.html').write_bytes(b'<p>synthetic</p>')
        p=self.root/'policy.json';p.write_text(json.dumps(policy()))
        self.build=SimpleNamespace(server=server,dist=dist,policy=policy(),proposal='f'*64,
            runtime={'policy':str(p)},steps=[{'name':n,'status':'passed'} for n in STEPS[:-1]])

    def test_report_binds_actual_bytes_without_adoption_or_deployment(self):
        descriptions=F.prepare(self.build,self.out)
        self.assertEqual([d['name'] for d in descriptions],['server','frontend.tar','verification.json'])
        for d in descriptions:
            raw=(self.out/d['name']).read_bytes()
            self.assertEqual(d,{'name':d['name'],'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
        report=json.loads((self.out/'verification.json').read_bytes())
        self.assertIs(report['production_authorized'],False)
        self.assertIs(report['independent_adoption_established'],False)
        self.assertEqual(report['steps'],[{'name':n,'status':'passed'} for n in STEPS])
        self.assertEqual(report['not_established'],list(LIMITS))
        self.assertEqual(report['proposal_sha256'],'f'*64)
        with tarfile.open(self.out/'frontend.tar') as archive:
            self.assertEqual(archive.getnames(),['index.html'])
            member=archive.getmembers()[0]
            self.assertEqual((member.uid,member.gid,member.mtime,member.mode),(0,0,0,0o444))
            self.assertEqual(archive.extractfile(member).read(),b'<p>synthetic</p>')

    def test_each_omitted_or_failed_step_cannot_produce_receipt(self):
        for index in range(len(STEPS)-1):
            complete=[{'name':n,'status':'passed'} for n in STEPS[:-1]]
            bad=copy.deepcopy(complete);bad[index]['status']='failed'
            for variant in (complete[:index]+complete[index+1:],bad,list(reversed(complete))):
                self.build.steps=variant
                with self.subTest(step=index),self.assertRaises(P.Refused):F.prepare(self.build,self.out)
                self.assertEqual(list(self.out.iterdir()),[])

    def test_frontend_symlink_cannot_escape(self):
        (self.build.dist/'escape').symlink_to(self.build.server)
        with self.assertRaises(P.Refused):F.prepare(self.build,self.out)
        self.assertFalse((self.out/'verification.json').exists())

    def test_existing_artifact_cannot_be_overwritten(self):
        target=self.out/'server';target.write_bytes(b'keep')
        with self.assertRaises(FileExistsError):F.prepare(self.build,self.out)
        self.assertEqual(target.read_bytes(),b'keep')
