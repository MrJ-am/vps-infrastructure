import json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'authority-v1'))
import test_admission_orchestrator
import staging_gate as T

class Gate(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.state=Path(self.tmp.name);self.state.chmod(0o700)
        (self.state/'records').mkdir(mode=0o700)
        self.job={'id':'a'*64,'phase':'validated','capture':{'proposal_sha256':'b'*64},'ready':{'base_sha256':'c'*64}}
        self.system='/nix/store/'+'d'*32+'-system'
        self.lease={**T.K.identity(self.job),'plan_sha256':'e'*64,'system':self.system}
        self.record={**self.lease,'phase':'ready','runtime':{'synthetic':'process-binding'}};self.probes=[];self.save()
    def save(self):
        T.O.save(self.state/'lease.json',self.lease)
        T.O.save(self.state/'records'/('e'*64+'.json'),self.record)
    def check(self,current=None,boot=None):
        return T.ready(self.state,self.job,observe=lambda:(current or self.system,boot or self.system),
            check_runtime=lambda record,lease:self.probes.append((record,lease)))
    def test_ready_record_matches_job_lease_live_and_boot(self):self.assertEqual(self.check(),self.lease)
    def test_readiness_probed_before_returning_approval(self):
        self.check();self.assertEqual(self.probes,[(self.record['runtime'],self.lease)])
    def test_all_incomplete_or_failed_phases_refused(self):
        for phase in ['prepared','tested','returned','active','boot','failed','recovery-required']:
            self.record['phase']=phase;self.save()
            with self.subTest(phase=phase),self.assertRaisesRegex(Exception,'STAGING_NOT_READY'):self.check()
    def test_job_or_base_or_digest_changed_refused(self):
        for key in ['job','proposal_sha256','base_sha256']:
            original=self.lease[key];self.lease[key]='f'*64;self.save()
            with self.subTest(key=key),self.assertRaisesRegex(Exception,'STAGING_LEASE_BINDING_REFUSED'):self.check()
            self.lease[key]=original
    def test_replayed_record_from_other_plan_or_system_refused(self):
        for key,value in [('plan_sha256','f'*64),('system','/nix/store/'+'f'*32+'-system')]:
            original=self.record[key];self.record[key]=value;self.save()
            with self.assertRaisesRegex(Exception,'STAGING_NOT_READY'):self.check()
            self.record[key]=original
    def test_current_and_boot_must_both_match(self):
        for current,boot in [('other',None),(None,'other')]:
            with self.assertRaisesRegex(Exception,'STAGING_LIVE_OR_BOOT_CHANGED'):self.check(current,boot)
    def test_prepared_candidate_cannot_substitute_for_staging_journal(self):
        self.record={'built':True,'ready_for_staging':True,'deployment_authorized':False};self.save()
        with self.assertRaisesRegex(Exception,'STAGING_NOT_READY'):self.check()
    def test_reserved_or_obsolete_job_refused(self):
        self.job['promotion']={'plan_sha256':'e'*64}
        with self.assertRaisesRegex(Exception,'STAGING_JOB_NOT_AVAILABLE'):self.check()
        del self.job['promotion'];self.job['phase']='obsolete'
        with self.assertRaisesRegex(Exception,'STAGING_JOB_NOT_AVAILABLE'):self.check()
    def test_symlink_or_world_writable_receipt_refused(self):
        path=self.state/'records'/('e'*64+'.json');path.chmod(0o666)
        with self.assertRaises(Exception):self.check()
        path.chmod(0o600);path.rename(self.state/'other');path.symlink_to(self.state/'other')
        with self.assertRaises(Exception):self.check()

if __name__=='__main__':unittest.main()
