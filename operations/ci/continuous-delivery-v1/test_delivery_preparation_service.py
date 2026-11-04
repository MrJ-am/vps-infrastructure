import json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
import test_promotion_service
os.environ.setdefault('MRJAM_DELIVERY_RECIPE',str(Path(__file__).resolve().parents[3]))
os.environ.setdefault('MRJAM_DELIVERY_NIX','/nix/store/'+'a'*32+'-nix')
import delivery_preparation_service as P

class Service(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.work=Path(self.tmp.name)
        self.path=lambda n:'/nix/store/'+'a'*32+'-'+n
        self.job={'id':'b'*64,'capture':{'proposal':{'repository':'mrjam-plateforme','repository_id':1437120781}}};self.environment={'system':self.path('system'),'active_slot':'blue',
            'slots':{'green':{'runtime':self.path('runtime')}}}
        self.binding={'schema_version':1,'proposal_sha256':'c'*64,'slot':'green','source':self.path('source'),
            'report_policy':self.path('policy')}
        self.candidate=self.path('candidate');self.changed_descriptor=False
        self.adapter=P.Adapter('synthetic-observer');self.adapter.observer=Mock()
        self.builder=Mock();self.builder.command.return_value=(self.candidate+'\n').encode()
        self.builder.return_value.construct.return_value={'built':True,'candidate':self.candidate}
        original=Path.read_bytes
        def read(path):
            if str(path)==self.candidate+'/descriptor.json':
                return json.dumps({'binding_sha256':P.O.sha((self.work/'binding.json').read_bytes()),
                    'proposal_sha256':'c'*64,'slot':'green','source':self.path('other' if self.changed_descriptor else 'source'),
                    'policy':self.path('policy'),'deployment_authorized':False}).encode()
            return original(path)
        self.environment_mock=Mock(return_value=self.environment)
        for obj,name,value in [(P.E,'read',self.environment_mock),(P.D,'binding',Mock(return_value=self.binding)),
                (P.B,'Builder',self.builder),(Path,'read_bytes',read)]:
            p=patch.object(obj,name,value);p.start();self.addCleanup(p.stop)
    def prepare(self):return self.adapter.prepare(self.work,self.work,self.job,self.environment)
    def test_result_is_staging_only_and_signature_rechecked(self):
        result=self.prepare();self.assertTrue(result['ready_for_staging']);self.assertFalse(result['deployment_authorized'])
        self.assertEqual(result['job'],self.job['id']);self.adapter.observer.verified.assert_called_once_with(self.work,self.job)
        self.assertEqual(P.D.binding.call_args.args[-1],self.adapter.observer.verified)
        self.adapter.observer.execute.assert_not_called()
    def test_unbound_candidate_never_reaches_generation_build(self):
        self.changed_descriptor=True
        with self.assertRaisesRegex(Exception,'PREPARATION_CANDIDATE_BINDING_REFUSED'):self.prepare()
        self.builder.return_value.construct.assert_not_called()
    def test_expired_authority_after_build_cannot_publish_readiness(self):
        self.adapter.observer.verified.side_effect=P.C.Refused('SIGNED_AUTHORITY_EXPIRED')
        with self.assertRaisesRegex(Exception,'SIGNED_AUTHORITY_EXPIRED'):self.prepare()
        self.assertFalse((self.work/'ready.json').exists())
    def test_changed_environment_after_build_refused(self):
        self.environment_mock.side_effect=[self.environment,{**self.environment,'system':self.path('other')}]
        with self.assertRaisesRegex(Exception,'PREPARATION_ENVIRONMENT_CHANGED'):self.prepare()
    def test_candidate_command_is_fixed_recipe_without_expression_argument(self):
        self.prepare();args=self.builder.command.call_args.args[0]
        self.assertTrue(args[1].endswith('/operations/ci/continuous-delivery-v1/delivery-candidate.nix'))
        self.assertNotIn('--expr',args);self.assertIn('--out-link',args)
    def test_reserved_stage_prevents_rebuilding_the_new_live_environment(self):
        lease=self.work/'lease.json';lease.write_text('{}')
        with patch.object(P.Q,'tick') as queue:
            self.assertEqual(P.tick(self.work,'synthetic-observer',lease=lease),{'code':'PREPARATION_STAGING_BUSY'})
            queue.assert_not_called()
        lease.unlink();lease.symlink_to(self.work/'absent')
        with patch.object(P.Q,'tick') as queue:
            self.assertEqual(P.tick(self.work,'synthetic-observer',lease=lease),{'code':'PREPARATION_STAGING_BUSY'})
            queue.assert_not_called()
    def test_released_stage_allows_next_preparation(self):
        with patch.object(P.Q,'tick',return_value={'code':'PREPARATION_IDLE'}) as queue:
            self.assertEqual(P.tick(self.work,'synthetic-observer',lease=self.work/'absent'),{'code':'PREPARATION_IDLE'})
            queue.assert_called_once()
    def vise_job(self):
        self.job['capture']['proposal']={'repository':'etp-vie-affective','repository_id':1433178398}
    def test_vise_disabled_cannot_prepare_or_block_platform_support(self):
        self.assertTrue(self.adapter.supports(self.job));self.vise_job()
        self.assertFalse(self.adapter.supports(self.job))
        with self.assertRaisesRegex(Exception,'PREPARATION_PROFILE_NOT_INSTALLED'):self.prepare()
        self.builder.command.assert_not_called()
    def test_forged_repository_identity_refused(self):
        self.vise_job();self.job['capture']['proposal']['repository_id']=1437120781
        with self.assertRaisesRegex(Exception,'DELIVERY_PROFILE_REPOSITORY_REFUSED'):self.prepare()
        self.builder.command.assert_not_called()
    def test_vise_uses_separate_builder_and_rechecks_authority(self):
        self.vise_job();binding={**self.binding,'verification_sha256':'d'*64}
        host=Mock();host.Builder.return_value.construct.return_value={'built':True,'profile':'vise-v1'}
        original=Path.read_bytes
        def read(path):
            if str(path)==self.candidate+'/descriptor.json':
                return json.dumps({'binding_sha256':P.O.sha((self.work/'binding.json').read_bytes()),
                    'proposal_sha256':'c'*64,'source':self.path('source'),'policy':self.path('policy'),
                    'deployment_authorized':False,'schema_version':2,'profile':'vise-v1',
                    'verification_sha256':'d'*64}).encode()
            return original(path)
        with patch.object(P,'ENABLE_VISE',True),patch.object(P.D,'vise_binding',return_value=binding),\
                patch.dict('sys.modules',{'host_builder':host}),patch.object(Path,'read_bytes',read):
            self.assertTrue(self.adapter.supports(self.job));result=self.prepare()
        self.assertTrue(result['ready_for_staging']);self.assertFalse(result['deployment_authorized'])
        self.assertIn('/operations/vise/delivery/content-candidate.nix',self.builder.command.call_args.args[0][1])
        host.Builder.return_value.construct.assert_called_once()
        self.builder.return_value.construct.assert_not_called()
        self.adapter.observer.verified.assert_called_once_with(self.work,self.job)

if __name__=='__main__':unittest.main()
