import json,unittest
from pathlib import Path
from unittest.mock import Mock,patch
import promotion_service as S

class Dispatch(unittest.TestCase):
    def setUp(self):
        self.state=Path('/synthetic/promotion');self.plan={'job':'a'*64}
        p=patch.object(S.C,'regular_file',side_effect=lambda *a,**kw:json.dumps(self.plan).encode())
        p.start();self.addCleanup(p.stop)
        self.adapter=Mock(key='b'*64,plan=self.plan)
    def test_platform_resumes_existing_plan(self):
        with patch.object(S,'Adapter',return_value=self.adapter) as adapter,\
                patch.object(S.T,'promote',return_value={'code':'PROMOTION_COMPLETE'}) as promote:
            self.assertEqual(S.resume(self.state)['code'],'PROMOTION_COMPLETE')
            adapter.assert_called_once_with(self.state);promote.assert_called_once_with(self.adapter)
    def test_vise_disabled_refuses_before_credentials_or_commands(self):
        self.plan['profile']='vise-v1'
        with patch.object(S,'credential') as credential,patch.object(S,'Adapter') as adapter:
            with self.assertRaisesRegex(Exception,'PROMOTION_PROFILE_NOT_INSTALLED'):S.resume(self.state)
            credential.assert_not_called();adapter.assert_not_called()
    def test_vise_dispatch_resumes_protocol_with_same_state(self):
        self.plan['profile']='vise-v1';module=Mock();module.Adapter.return_value=self.adapter
        protocol=Mock();protocol.promote.return_value={'code':'VISE_RECOVERY_REQUIRED'}
        with patch.object(S,'ENABLE_VISE',True),patch.object(S,'credential',return_value='synthetic-reader'),\
                patch.dict('sys.modules',{'transition_adapter':module,'transition':protocol}),\
                patch.object(S,'Adapter') as platform:
            result=S.resume(self.state)
        self.assertEqual(result['code'],'VISE_RECOVERY_REQUIRED');self.assertEqual(result['plan_sha256'],'b'*64)
        module.Adapter.assert_called_once_with(self.state,'synthetic-reader')
        protocol.promote.assert_called_once_with(self.adapter);platform.assert_not_called()
    def test_unknown_profile_cannot_fall_back_to_platform(self):
        self.plan['profile']='arbitrary'
        with patch.object(S,'Adapter') as adapter:
            with self.assertRaisesRegex(Exception,'PROMOTION_PROFILE_REFUSED'):S.resume(self.state)
            adapter.assert_not_called()
    def test_disabled_tick_keeps_platform_resume_path(self):
        with patch.object(S,'resume',return_value={'code':'PROMOTION_COMPLETE'}) as resume:
            self.assertEqual(S.tick(self.state)['code'],'PROMOTION_COMPLETE')
            resume.assert_called_once_with(self.state)
    def test_enabled_tick_publishes_without_activation_in_same_tick(self):
        queue=Mock();queue.tick.return_value={'code':'PROMOTION_PLAN_ENQUEUED'}
        with patch.object(S,'ENABLE_VISE',True),patch.dict('sys.modules',{'queue_tick':queue}),\
                patch.object(S,'resume') as resume:
            self.assertEqual(S.tick(self.state)['code'],'PROMOTION_PLAN_ENQUEUED')
            resume.assert_not_called();queue.tick.assert_called_once_with(self.state,S.credential)
    def test_enabled_tick_resumes_active_transition(self):
        queue=Mock();queue.tick.return_value=None
        with patch.object(S,'ENABLE_VISE',True),patch.dict('sys.modules',{'queue_tick':queue}),\
                patch.object(S,'resume',return_value={'code':'VISE_COMPLETE'}) as resume:
            self.assertEqual(S.tick(self.state)['code'],'VISE_COMPLETE')
            resume.assert_called_once_with(self.state)

if __name__=='__main__':unittest.main()
