import hashlib,json,tempfile,tarfile,unittest
from pathlib import Path
from types import SimpleNamespace
import artifacts as F,authority_profile as A,source_policy as P

class Artifacts(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        r=Path(self.tmp.name);self.output=r/'output';self.output.mkdir()
        server=r/'binary';server.write_bytes(b'\x7fELFsynthetic-only')
        dist=r/'dist';dist.mkdir();(dist/'index.html').write_text('<html lang="fr"></html>')
        policy={'schema_version':2,'status':'proposed-not-independently-adopted','profile':'vise-v1',
            'rules_revision':'a'*40,'sources':[{'id':'vise','repository':'MrJ-am/etp-vie-affective',
                'revision':'b'*40,'tree_sha':'c'*40,'root':P.ROOT,'tree_json':P.TREE}],
            'frontends':[],'rust_manifests':{name:'d'*64 for name in P.MANIFESTS},'out_of_scope':P.OUT_OF_SCOPE}
        file=r/'policy.json';file.write_text(json.dumps(policy))
        self.build=SimpleNamespace(server=server,dist=dist,policy=policy,proposal='e'*64,
            runtime={'policy':str(file)},steps=[{'name':n,'status':'passed'} for n in A.REQUIRED_STEPS[:-1]])

    def test_exact_bytes_bound_without_production_authority(self):
        descriptions=F.prepare(self.build,self.output)
        for item in descriptions:
            raw=(self.output/item['name']).read_bytes()
            self.assertEqual((len(raw),hashlib.sha256(raw).hexdigest()),(item['bytes'],item['sha256']))
        report=json.loads((self.output/'verification.json').read_bytes())
        self.assertFalse(report['production_authorized']);self.assertFalse(report['independent_adoption_established'])
        self.assertEqual([s['name'] for s in report['steps']],list(A.REQUIRED_STEPS))
        with tarfile.open(self.output/'frontend.tar') as archive:
            self.assertEqual(archive.getnames(),['index.html'])
            member=archive.getmembers()[0]
            self.assertEqual((member.uid,member.gid,member.mtime,member.mode),(0,0,0,0o444))
            self.assertEqual(archive.extractfile(member).read(),(self.build.dist/'index.html').read_bytes())

    def test_missing_runtime_step_refused(self):
        self.build.steps.pop()
        with self.assertRaisesRegex(P.Refused,'INCOMPLETE_VALIDATION'):F.prepare(self.build,self.output)
        self.assertEqual(list(self.output.iterdir()),[])

    def test_frontend_link_refused(self):
        (self.build.dist/'escape').symlink_to(self.build.server)
        with self.assertRaisesRegex(P.Refused,'FRONTEND_ARTIFACT_REFUSED'):F.prepare(self.build,self.output)
        self.assertFalse((self.output/'verification.json').exists())

    def test_existing_output_not_overwritten(self):
        (self.output/'server').write_bytes(b'keep')
        with self.assertRaises(FileExistsError):F.prepare(self.build,self.output)
        self.assertEqual((self.output/'server').read_bytes(),b'keep')

if __name__=='__main__':unittest.main()
