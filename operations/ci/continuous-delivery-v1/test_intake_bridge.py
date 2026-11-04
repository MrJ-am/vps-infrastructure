import json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import test_intake_queue as T
import intake_bridge as B

class Bridge(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.spool=self.root/'prepared';self.spool.mkdir(mode=0o700)
        self.inbox=self.root/'decisions';self.inbox.mkdir(mode=0o755)
        self.q=T.Q.Queue(self.root);self.addCleanup(self.q.close)
        proposal=T.proposal();self.q.observe([proposal],1);claim=self.q.claim(2)
        identity={'schema_version':1,'job_key':claim['key'],'proposal':proposal,'base_sha256':'a'*64,'base_policy_sha256':'b'*64}
        self.path=self.spool/B.sha(B.encode(identity));self.path.mkdir(mode=0o700)
        receipt={**identity,'proposal_sha256':'c'*64,'policy_sha256':'d'*64,'deployment_authorized':False}
        raw=B.encode(receipt);(self.path/'receipt.json').write_bytes(raw)
        (self.path/'source').mkdir();(self.path/'source/code.rs').write_text('// invented')
        self.receipt=B.sha(raw);self.key=claim['key'];self.q.finish(claim,3,receipt=self.receipt)
    def decision(self,action='captured',receipt=None):
        receipt=receipt or self.receipt
        path=self.inbox/(self.key+'-'+receipt+'.json')
        path.write_bytes(B.encode({'schema_version':1,'key':self.key,'receipt':receipt,'action':action}));path.chmod(0o444)
        return path
    def apply(self):return B.decisions(self.q,self.spool,self.inbox,4,owner=os.getuid())
    def test_export_contains_only_bound_metadata(self):
        self.assertEqual(B.export(self.q,self.spool,self.root),1)
        snapshot=json.loads((self.root/'ready.json').read_bytes())
        self.assertEqual(snapshot['ready'][0]['job'],self.q.ready()[0]);self.assertFalse(snapshot['deployment_authorized'])
        self.assertNotIn('code.rs',(self.root/'ready.json').read_text())
    def test_capture_acknowledges_and_retires_only_exact_result(self):
        self.decision();self.assertEqual(self.apply(),1);self.assertEqual(self.q.ready(),[])
        self.assertFalse(self.path.exists());self.assertEqual(B.export(self.q,self.spool,self.root),0)
        self.assertEqual(self.q.db.execute('SELECT state FROM jobs').fetchone()[0],'consumed')
    def test_crash_after_ack_before_retirement_recovers(self):
        self.decision()
        with patch.object(B.shutil,'rmtree',side_effect=OSError('invented interruption')):
            B.shutil.rmtree.avoids_symlink_attacks=True
            with self.assertRaises(OSError):self.apply()
        self.assertTrue(self.path.exists());self.assertEqual(self.q.ready(),[])
        self.assertEqual(self.apply(),1);self.assertFalse(self.path.exists())
    def test_reprepare_is_recovered_after_sqlite_commit(self):
        self.decision('reprepare');self.q.reprepare(self.key,self.receipt,4)
        self.assertEqual(self.apply(),1);self.assertEqual(self.q.claim(5)['key'],self.key)
    def test_old_receipt_does_not_acknowledge_new_result(self):
        self.decision(receipt='f'*64);self.assertEqual(self.apply(),0)
        self.assertEqual(len(self.q.ready()),1);self.assertTrue(self.path.exists())
    def test_writable_decision_refused(self):
        self.decision().chmod(0o644)
        with self.assertRaisesRegex(B.Q.S.Refused,'BRIDGE_DECISION_FILE'):self.apply()
        self.assertEqual(len(self.q.ready()),1);self.assertTrue(self.path.exists())
    def test_symlink_decision_refused(self):
        path=self.decision();target=self.root/'outside';path.rename(target);path.symlink_to(target)
        with self.assertRaises(OSError):self.apply()
        self.assertTrue(self.path.exists())
    def test_wrong_owner_directory_refused(self):
        with self.assertRaisesRegex(B.Q.S.Refused,'BRIDGE_DECISION_DIRECTORY'):
            B.decisions(self.q,self.spool,self.inbox,4,owner=os.getuid()+1)
    def test_extra_decision_field_cannot_execute_code(self):
        path=self.decision();value=json.loads(path.read_bytes());value['command']='invented'
        path.chmod(0o600);path.write_bytes(B.encode(value));path.chmod(0o444)
        with self.assertRaisesRegex(B.Q.S.Refused,'BRIDGE_DECISION_FIELDS'):self.apply()
        self.assertTrue(self.path.exists())

if __name__=='__main__':unittest.main()
