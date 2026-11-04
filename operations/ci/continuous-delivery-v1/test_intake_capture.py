"""Treat prepared source files and policy as hostile across the intake boundary."""
import json,os,shutil,unittest
from unittest.mock import patch
import test_intake_prepare as T
import intake_capture as C

class Capture(unittest.TestCase):
    def setUp(self):
        self.fixture=T.IntakePreparation('runTest');self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        f=self.fixture;f.q.observe([f.proposal],1);ready=f.run_once()
        self.assertEqual(ready['code'],'PREPARATION_READY')
        self.input=f.spool/ready['result'];self.job=f.q.ready()[0]
        self.parent=f.root/'protected';self.parent.mkdir(mode=0o700)
        self.output=self.parent/'capture';self.observations=0;self.base_checks=0
    def observe(self,proposal):
        self.observations+=1;self.assertEqual(proposal,self.fixture.proposal)
        return {'repository':'MrJ-am/mrjam-plateforme','revision':proposal['head'],
            'tree_sha':self.fixture.fixture.git('rev-parse',proposal['head']+'^{tree}')}
    def still_adopted(self):self.base_checks+=1;return True
    def capture(self,**kwargs):
        return C.capture(self.fixture.spool,self.output,self.job,T.B.DIGEST,T.B.POLICY,
            intake_uid=kwargs.get('owner',os.getuid()),validator_policy=T.B.P,gate_path=T.B.GATE,
            observe=kwargs.get('observe',self.observe),still_adopted=kwargs.get('still_adopted',self.still_adopted))
    def alter_receipt(self,edit):
        receipt=json.loads((self.input/'receipt.json').read_bytes());edit(receipt)
        raw=C.encode(receipt);(self.input/'receipt.json').write_bytes(raw);self.job['receipt']=C.sha(raw)
    def test_real_capture_verifies_with_independent_commit_tree(self):
        result=self.capture()
        self.assertTrue(result['independently_verified']);self.assertFalse(result['deployment_authorized'])
        self.assertEqual(self.observations,1);self.assertEqual(self.base_checks,2)
        self.assertEqual((self.output/'source/manifest.json').read_bytes(),(self.input/'source/manifest.json').read_bytes())
        self.assertEqual((self.output/'capture.json').stat().st_mode&0o777,0o400)
    def test_symlink_leaf_never_read_and_partial_removed(self):
        source=self.input/'source/sources/platform/Cargo.toml';source.unlink()
        secret=self.fixture.root/'unrelated';secret.write_text('invented unrelated content')
        source.symlink_to(secret)
        with self.assertRaises(OSError):self.capture()
        self.assertFalse(self.output.exists());self.assertEqual(self.observations,0)
    def test_symlink_ancestor_refused(self):
        source=self.input/'source/sources/platform';moved=self.fixture.root/'outside';source.rename(moved);source.symlink_to(moved)
        with self.assertRaises(OSError):self.capture()
        self.assertFalse(self.output.exists())
    def test_hardlink_refused(self):
        source=self.input/'source/sources/platform/Cargo.toml'
        os.link(source,self.fixture.root/'other-link')
        with self.assertRaisesRegex(C.Q.S.Refused,'CAPTURE_FILE_REFUSED'):self.capture()
        self.assertFalse(self.output.exists())
    def test_fifo_refused_without_blocking(self):
        source=self.input/'source/sources/platform/Cargo.toml';source.unlink();os.mkfifo(source,0o600)
        with self.assertRaisesRegex(C.Q.S.Refused,'CAPTURE_FILE_REFUSED'):self.capture()
        self.assertFalse(self.output.exists())
    def test_wrong_owner_refused_before_copy(self):
        with self.assertRaisesRegex(C.Q.S.Refused,'CAPTURE_DIRECTORY_REFUSED'):self.capture(owner=os.getuid()+1)
        self.assertFalse(self.output.exists())
    def test_receipt_self_consistent_but_forged_policy_refused(self):
        path=self.input/'policy.json';policy=json.loads(path.read_bytes())
        next(s for s in policy['sources'] if s['id']=='vision')['revision']='a'*40
        raw=C.encode(policy);path.write_bytes(raw)
        self.alter_receipt(lambda receipt:receipt.update(policy_sha256=C.sha(raw)))
        with self.assertRaisesRegex(C.Q.S.Refused,'INTAKE_POLICY_CHANGED'):self.capture()
        self.assertFalse(self.output.exists());self.assertEqual(self.observations,1)
    def test_fresh_remote_tree_cannot_be_replaced_with_receipt(self):
        def wrong(proposal):return {**self.observe(proposal),'tree_sha':'0'*40}
        with self.assertRaisesRegex(C.Q.S.Refused,'INTAKE_POLICY_CHANGED'):self.capture(observe=wrong)
        self.assertFalse(self.output.exists())
    def test_changed_adopted_base_after_observation_removes_capture(self):
        responses=iter([True,False])
        with self.assertRaisesRegex(C.Q.S.Refused,'ADOPTED_BASE_CHANGED'):
            self.capture(still_adopted=lambda:next(responses))
        self.assertFalse(self.output.exists());self.assertEqual(self.observations,1)
    def test_old_base_rejected_before_read(self):
        with self.assertRaisesRegex(C.Q.S.Refused,'ADOPTED_BASE_CHANGED'):self.capture(still_adopted=lambda:False)
        self.assertFalse(self.output.exists());self.assertEqual(self.observations,0)
    def test_existing_destination_retained(self):
        self.output.mkdir(mode=0o700);(self.output/'retained').write_text('invented previous capture')
        with self.assertRaises(FileExistsError):self.capture()
        self.assertEqual((self.output/'retained').read_text(),'invented previous capture')
    def test_unlisted_files_are_not_copied(self):
        (self.input/'source/unlisted').write_text('invented file outside the manifest')
        self.capture();self.assertFalse((self.output/'source/unlisted').exists())
    def test_metadata_digest_mismatch_refused(self):
        self.job['receipt']='0'*64
        with self.assertRaisesRegex(C.Q.S.Refused,'CAPTURE_RECEIPT_DIGEST'):self.capture()
        self.assertFalse(self.output.exists())
    def test_changed_file_during_fd_read_refused(self):
        original=C.os.fstat;calls={}
        def altered(fd):
            value=original(fd)
            path=os.readlink('/proc/self/fd/'+str(fd))
            if path.endswith('/receipt.json'):
                calls[fd]=calls.get(fd,0)+1
                if calls[fd]==2:
                    # A write after the read changes ctime/mtime even if bytes
                    # and length are unchanged; the captured FD sees it.
                    p=self.input/'receipt.json';p.write_bytes(p.read_bytes());value=original(fd)
            return value
        with patch.object(C.os,'fstat',side_effect=altered):
            with self.assertRaisesRegex(C.Q.S.Refused,'CAPTURE_FILE_CHANGED'):self.capture()
        self.assertFalse(self.output.exists())

if __name__=='__main__':unittest.main()
