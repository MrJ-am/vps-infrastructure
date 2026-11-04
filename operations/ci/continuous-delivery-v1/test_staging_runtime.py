import json,unittest
from unittest.mock import patch
import test_source_observation
import staging_runtime as R

class Runtime(unittest.TestCase):
    def setUp(self):
        self.record={'slot':'green','server':'/nix/store/'+'a'*32+'-server','runtime':'/nix/store/'+'b'*32+'-runtime',
            'pid':123,'starttime':456,'boot_id':'11111111-2222-3333-4444-555555555555'}
        self.identity={k:self.record[k] for k in ('pid','starttime','boot_id')}
        self.environment={'active_slot':'blue','slots':{'green':{k:self.record[k] for k in ('server','runtime')}}}
        self.response={'status':'ready','scope':'configured-capabilities-only','capabilities':['synthetic']}
    def verify(self,**kwargs):
        R.verify(self.record,self.environment,observe=kwargs.get('observe',lambda slot:self.identity),
            request=kwargs.get('request',lambda slot:self.response),read=lambda path:json.dumps({'required_capabilities':['synthetic']}).encode())
    def test_live_qualified_process_is_ready(self):self.verify()
    def test_pid_reuse_restart_or_reboot_invalidates_readiness(self):
        for key,value in [('pid',124),('starttime',457),('boot_id','00000000-2222-3333-4444-555555555555')]:
            with self.subTest(key=key),self.assertRaisesRegex(Exception,'STAGING_RUNTIME_PROCESS_CHANGED'):
                self.verify(observe=lambda slot:{**self.identity,key:value})
    def test_process_changed_during_http_probe_refused(self):
        observations=iter([self.identity,{**self.identity,'starttime':999}])
        with self.assertRaisesRegex(Exception,'STAGING_RUNTIME_PROCESS_CHANGED'):
            self.verify(observe=lambda slot:next(observations))
    def test_capability_mismatch_refused(self):
        with self.assertRaisesRegex(Exception,'STAGING_RUNTIME_CAPABILITIES_REFUSED'):
            self.verify(request=lambda slot:{**self.response,'capabilities':[]})
    def test_public_slot_cannot_be_tested_as_inactive(self):
        self.environment['active_slot']='green'
        with self.assertRaisesRegex(Exception,'STAGING_RUNTIME_BINDING_REFUSED'):self.verify()
    def test_changed_server_or_runtime_binding_refused(self):
        for key in ['server','runtime']:
            original=self.environment['slots']['green'][key]
            self.environment['slots']['green'][key]='/nix/store/'+'c'*32+'-other'
            with self.assertRaisesRegex(Exception,'STAGING_RUNTIME_BINDING_REFUSED'):self.verify()
            self.environment['slots']['green'][key]=original
    def test_capture_requires_exact_elf_and_rechecks_afterward(self):
        with patch.object(R,'process',return_value=self.identity),patch.object(R.os,'readlink',return_value='/other/executable'),\
                patch.object(R,'verify') as verify:
            with self.assertRaisesRegex(Exception,'STAGING_RUNTIME_EXECUTABLE_REFUSED'):R.capture('green',self.environment)
            verify.assert_not_called()
        with patch.object(R,'process',return_value=self.identity),\
                patch.object(R.os,'readlink',return_value=self.record['server']+'/libexec/mrjam-server'),patch.object(R,'verify') as verify:
            self.assertEqual(R.capture('green',self.environment),self.record);verify.assert_called_once_with(self.record,self.environment)
    def test_proc_stat_with_spaces_or_parentheses_in_name(self):
        raw='123 (a tricky) name) '+' '.join(['S']+['0']*18+['456']+['0']*5)
        values={'/sys/fs/cgroup/mrjam.slice/mrjam-rust.slice/mrjam-rust-green.service/cgroup.procs':b'123\n',
            '/proc/123/stat':raw.encode(),'/proc/sys/kernel/random/boot_id':self.identity['boot_id'].encode()}
        with patch.object(R,'code',side_effect=lambda path:values[path]):self.assertEqual(R.process('green'),self.identity)
    def test_multiple_processes_cannot_impersonate_single_qualified_server(self):
        with patch.object(R,'code',return_value=b'123\n124\n'):
            with self.assertRaisesRegex(Exception,'STAGING_RUNTIME_PROCESS_REFUSED'):R.process('green')

if __name__=='__main__':unittest.main()
