import json,tempfile,tarfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
import test_preparation_plan
from test_package_content import archive
import vise_verified_delivery as V

class Content(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'bundle';self.server=Path(self.tmp.name)/'server'
        (self.root/'dist').mkdir(parents=True);(self.server/'bin').mkdir(parents=True);(self.server/'libexec').mkdir()
        self.artifacts={'server':b'synthetic server','frontend.tar':archive([('index.html',b'html',tarfile.REGTYPE)])}
        (self.server/'libexec/mrjam-server').write_bytes(self.artifacts['server'])
        (self.server/'bin/mrjam-server').write_text('synthetic wrapper')
        (self.root/'server').symlink_to(self.server/'bin/mrjam-server')
        (self.root/'dist/index.html').write_bytes(b'html')
        self.digest='a'*64
        self.manifest={'schema_version':1,'profile':'vise-v1','proposal_sha256':self.digest,
            'server':str(self.server),'server_sha256':V.C.sha(self.artifacts['server']),
            'frontend_archive_sha256':V.C.sha(self.artifacts['frontend.tar']),
            'frontend_files':{'index.html':V.C.sha(b'html')},'deployment_authorized':False}
        self.save()
        # Only path validation is adapted for filesystem fixtures; actual bytes,
        # archive, link target and inventory checks remain active.
        p=patch.object(V.G,'store',return_value=True);p.start();self.addCleanup(p.stop)
    def save(self):(self.root/'artifact.json').write_text(json.dumps(self.manifest))
    def check(self):return V.content(str(self.root),self.digest,self.artifacts)
    def test_exact_content_passes(self):self.assertEqual(self.check(),self.manifest)
    def test_server_mutation_refused(self):
        (self.server/'libexec/mrjam-server').write_bytes(b'changed')
        with self.assertRaisesRegex(Exception,'VISE_DELIVERY_SERVER_CHANGED'):self.check()
    def test_frontend_mutation_refused(self):
        (self.root/'dist/index.html').write_bytes(b'bad!')
        with self.assertRaisesRegex(Exception,'VISE_DELIVERY_FRONTEND_CHANGED'):self.check()
    def test_extra_file_or_directory_refused(self):
        for directory in (False,True):
            path=self.root/'dist/extra'
            if directory:path.mkdir()
            else:path.write_bytes(b'x')
            with self.assertRaises(Exception):self.check()
            if directory:path.rmdir()
            else:path.unlink()
    def test_symlinked_web_file_refused(self):
        p=self.root/'dist/index.html';p.unlink();p.symlink_to(self.server/'bin/mrjam-server')
        with self.assertRaisesRegex(Exception,'VISE_DELIVERY_TREE_REFUSED'):self.check()
    def test_different_wrapper_target_refused(self):
        p=self.root/'server';p.unlink();p.symlink_to(self.server/'libexec/mrjam-server')
        with self.assertRaisesRegex(Exception,'VISE_DELIVERY_EXECUTABLE_CHANGED'):self.check()
    def test_manifest_cannot_relabel_signed_payload(self):
        self.manifest['proposal_sha256']='b'*64;self.save()
        with self.assertRaisesRegex(Exception,'VISE_DELIVERY_MANIFEST_CHANGED'):self.check()
    def test_missing_web_file_refused(self):
        (self.root/'dist/index.html').unlink()
        with self.assertRaisesRegex(Exception,'VISE_DELIVERY_FRONTEND_MISSING'):self.check()

class Authority(unittest.TestCase):
    def setUp(self):
        self.p=lambda n:'/nix/store/'+'a'*32+'-'+n
        self.source=b'synthetic manifest';self.digest=V.C.sha(self.source)
        self.job={'id':'b'*64,'phase':'validated','capture':{'proposal_sha256':self.digest,
            'proposal':{'repository':'etp-vie-affective','repository_id':1433178398,'head':'c'*40}},'run':{'id':7}}
        self.plan={'profile':'vise-v1','job':self.job['id'],'proposal_sha256':self.digest,
            'candidate':self.p('candidate'),'bundle':self.p('bundle'),'adopted':self.p('adopted'),'forge_pull':3,'review':{}}
        self.artifacts={n:n.encode() for n in ('server','frontend.tar','verification.json')}
        self.envelope={'payload':{'proposal_sha256':self.digest,'artifacts':[
            {'name':n,'bytes':len(b),'sha256':V.C.sha(b)} for n,b in self.artifacts.items()]}}
        self.policy={'rules_revision':'d'*40,'report_policy_sha256':V.C.sha(b'policy'),
            'sources':[{'repository':'MrJ-am/etp-vie-affective','revision':'c'*40}]}
        self.candidate={'schema_version':2,'profile':'vise-v1','deployment_authorized':False,
            'proposal_sha256':self.digest,'bundle':self.plan['bundle'],'adopted':self.plan['adopted'],
            'source':self.p('source'),'policy':self.p('policy'),'verification_sha256':V.C.sha(self.artifacts['verification.json'])}
        def read(path,maximum):
            path=str(path)
            if path.endswith('/descriptor.json'):return json.dumps(self.candidate).encode()
            if path.endswith('/manifest.json'):return self.source
            if path==self.plan['adopted']:return json.dumps({'schema_version':1,'source':self.p('source'),
                'policy':self.p('policy'),'proposal_sha256':self.digest}).encode()
            return b'policy'
        def regular(path,**kw):
            return json.dumps(self.envelope).encode() if path.name=='attestation.json' else self.artifacts[path.name]
        self.api=Mock(return_value={'merged':True});self.response=Mock(status=200)
        self.response.read.return_value=b'{"id":7}';self.connection=Mock();self.connection.getresponse.return_value=self.response
        replacements=[(V.O.W,'private_directory',lambda p:p),(V.O,'read',lambda p:self.job),
            (V.A,'load',lambda d:{'authority':self.policy,'details':{'profile':'vise-v1','report_policy':self.p('policy')}}),
            (V.C,'regular_file',regular),(V,'read',read),(V.signer,'verify',Mock(return_value=True)),
            (V,'content',Mock(return_value={'verified':'content'})),(V.M,'API',Mock(return_value=self.api)),
            (V.M,'merge',Mock()),(V.D,'identify',Mock(return_value={'terminal':True,'status':'success'})),
            (V.http.client,'HTTPConnection',Mock(return_value=self.connection))]
        for obj,name,value in replacements:
            p=patch.object(obj,name,value);p.start();self.addCleanup(p.stop)
    def verify(self):return V.verify(self.plan,'synthetic-observer',jobs=Path('/synthetic/jobs'))
    def test_rechecks_signature_content_run_and_protected_merge(self):
        self.assertEqual(self.verify(),{'verified':'content'})
        V.signer.verify.assert_called_once();V.content.assert_called_once();V.M.merge.assert_called_once()
    def test_expired_signature_stops_before_remote_or_content(self):
        V.signer.verify.return_value=False
        with self.assertRaisesRegex(Exception,'VISE_DELIVERY_SIGNATURE_REFUSED'):self.verify()
        V.content.assert_not_called();V.M.API.assert_not_called()
    def test_changed_signed_bytes_refused(self):
        self.artifacts['server']=b'changed'
        with self.assertRaisesRegex(Exception,'VISE_DELIVERY_SIGNED_BYTES_CHANGED'):self.verify()
    def test_unmerged_proposal_cannot_trigger_merge(self):
        self.api.return_value={'merged':False}
        with self.assertRaisesRegex(Exception,'VISE_DELIVERY_MERGE_REQUIRED'):self.verify()
        V.M.merge.assert_not_called()
    def test_race_to_remote_write_is_refused(self):
        def attempt(*args,**kwargs):args[6]('POST','/merge',{})
        V.M.merge.side_effect=attempt
        with self.assertRaisesRegex(Exception,'VISE_DELIVERY_REMOTE_WRITE_REFUSED'):self.verify()
        self.assertTrue(all(c.args[0]=='GET' for c in self.api.call_args_list))
    def test_changed_ci_run_refused(self):
        self.response.read.return_value=b'{"id":8}'
        with self.assertRaisesRegex(Exception,'VISE_DELIVERY_RUN_CHANGED'):self.verify()
    def test_failed_ci_refused(self):
        V.D.identify.return_value={'terminal':True,'status':'failure'}
        with self.assertRaisesRegex(Exception,'VISE_DELIVERY_RUN_NOT_SUCCESSFUL'):self.verify()

if __name__=='__main__':unittest.main()
