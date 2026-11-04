import json,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
import test_promotion_service
import delivery_constructor as D

class Constructor(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/('a'*64);self.root.mkdir(mode=0o700)
        self.store=Path(self.tmp.name)/'store';self.store.mkdir()
        self.name=lambda n:'/nix/store/'+'a'*32+'-'+n
        self.job={'schema_version':1,'id':'a'*64,'phase':'validated','bundle':self.name('bundle'),
            'capture':{'proposal_sha256':'b'*64,'proposal':{'repository':'mrjam-plateforme','head':'c'*40}}}
        self.policy={'rules_revision':'d'*40,'report_policy_sha256':D.C.sha(b'policy')}
        self.raw={'server':b'server','frontend.tar':b'frontend','verification.json':b'report'}
        self.envelope={'payload':{'proposal_sha256':'b'*64,'artifacts':[
            {'name':n,'bytes':len(raw),'sha256':D.C.sha(raw)} for n,raw in self.raw.items()]}}
        self.verify=Mock(return_value=(self.job['capture']['proposal'],self.policy,self.envelope,{},{}))
        (self.root/'capture').mkdir();(self.root/'capture/capture.json').write_bytes(b'capture')
        self.descriptor={'proposal_sha256':'b'*64,'capture_sha256':D.C.sha(b'capture'),'source':self.name('source')}
        (self.store/'bundle').mkdir();self.save_descriptor()
        (self.store/'policy').write_bytes(b'policy')
        original=D.store
        def store(value):original(value);return self.store/value.split('-',1)[1]
        for obj,name,replacement in [(D,'store',store),(D.O,'read',lambda p:self.job),
            (D.O.W,'private_directory',lambda p:p),(D.O.W,'read_file',lambda p,n:p.read_bytes()),
            (D.A,'load',lambda d:{'authority':self.policy,'details':{'report_policy':self.name('policy')}}),
            (D,'source',Mock()),(D.C,'regular_file',lambda p,**kwargs:self.raw[p.name])]:
            p=patch.object(obj,name,replacement);p.start();self.addCleanup(p.stop)
    def save_descriptor(self):(self.store/'bundle/descriptor.json').write_text(json.dumps(self.descriptor))
    def binding(self):return D.binding(self.root,self.job,'green',self.name('runtime'),self.verify)
    def test_success_binds_exact_hashes(self):
        b=self.binding();self.assertEqual(b['proposal_sha256'],'b'*64)
        self.assertEqual(b['server_sha256'],D.C.sha(b'server'));self.assertEqual(b['server_bytes'],6)
        self.assertEqual(b['slot'],'green');self.verify.assert_called_once()
    def test_missing_recipe_never_reaches_verifier(self):
        for repository in ('Signature','etp-vie-affective'):
            self.job['capture']['proposal']['repository']=repository
            with self.assertRaisesRegex(Exception,'CONSTRUCTION_RECIPE_NOT_AVAILABLE'):self.binding()
        self.verify.assert_not_called()
    def test_invalid_signature_stops_binding(self):
        self.verify.side_effect=D.C.Refused('SYNTHETIC_SIGNATURE_REFUSED')
        with patch.object(D.A,'load') as load:
            with self.assertRaisesRegex(Exception,'SYNTHETIC_SIGNATURE_REFUSED'):self.binding()
            load.assert_not_called()
    def test_changed_capture_refused(self):
        self.descriptor['capture_sha256']='f'*64;self.save_descriptor()
        with self.assertRaisesRegex(Exception,'CONSTRUCTION_CAPTURE_BINDING_REFUSED'):self.binding()
    def test_arbitrary_source_path_refused(self):
        self.descriptor['source']='/tmp/untrusted';self.save_descriptor()
        with self.assertRaisesRegex(Exception,'CONSTRUCTION_STORE_PATH_REFUSED'):self.binding()
    def test_changed_signed_bytes_refused(self):
        self.raw['server']=b'changed'
        with self.assertRaisesRegex(Exception,'CONSTRUCTION_ARTIFACT_CHANGED'):self.binding()
    def test_changed_policy_refused(self):
        (self.store/'policy').write_bytes(b'changed')
        with self.assertRaisesRegex(Exception,'CONSTRUCTION_POLICY_CHANGED'):self.binding()
    def test_reserved_job_not_repackaged(self):
        self.job['promotion']={}
        with self.assertRaisesRegex(Exception,'CONSTRUCTION_JOB_NOT_AVAILABLE'):self.binding()
        self.verify.assert_not_called()

    def vise(self,profile='vise-v1'):
        self.job['capture']['proposal'].update(repository='etp-vie-affective',repository_id=1433178398)
        admitted={'authority':self.policy,'details':{'report_policy':self.name('policy'),'profile':profile}}
        with patch.object(D.A,'load',return_value=admitted):return D.vise_binding(self.root,self.job,self.verify)
    def test_vise_binding_has_own_profile_and_no_monolith_slot(self):
        result=self.vise()
        self.assertEqual(result['profile'],'vise-v1');self.assertEqual(result['schema_version'],2)
        self.assertNotIn('slot',result);self.assertNotIn('runtime',result)
        self.assertEqual(result['verification_sha256'],D.C.sha(b'report'))
    def test_vise_rejects_platform_authority(self):
        with self.assertRaisesRegex(Exception,'CONSTRUCTION_PROFILE_CHANGED'):self.vise('platform')
    def test_vise_rechecks_artifact_bytes(self):
        self.raw['frontend.tar']=b'changed'
        with self.assertRaisesRegex(Exception,'CONSTRUCTION_ARTIFACT_CHANGED'):self.vise()
    def test_vise_signature_failure_precedes_content_binding(self):
        self.verify.side_effect=D.C.Refused('SYNTHETIC_SIGNATURE_REFUSED')
        with self.assertRaisesRegex(Exception,'SYNTHETIC_SIGNATURE_REFUSED'):self.vise()

if __name__=='__main__':unittest.main()
