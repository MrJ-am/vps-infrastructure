"""Private synthetic files; no real bundle, production path, Git or service."""
import fcntl
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import retain_previous_infrastructure_bundle as m


class RetainTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='retain-infra-test-',dir=Path(__file__).resolve().parents[2]/'.local')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.state=self.root/'state';self.state.mkdir(mode=0o700)
        self.source=self.root/'sources';self.source.mkdir(mode=0o700)
        self.payload=b'INVENTED INFRASTRUCTURE BUNDLE\n'
        self.old_umask=os.umask(0o077);self.addCleanup(os.umask,self.old_umask)
        for key,value in {'STATE':self.state,'SOURCE':self.source,'OWNER':(os.geteuid(),os.getegid()),
                          'BYTES':len(self.payload),'SHA256':hashlib.sha256(self.payload).hexdigest()}.items():
            p=patch.object(m,key,value);p.start();self.addCleanup(p.stop)
        p=patch.object(m.os.path,'realpath',return_value=m.PREVIOUS);p.start();self.addCleanup(p.stop)
        self.lock=self.state/'transaction.lock';self.lock.write_bytes(b'');self.lock.chmod(0o600)
        self.bundle=self.source/m.BUNDLE;self.bundle.write_bytes(self.payload);self.bundle.chmod(0o600)
        self.other=self.source/'another.bundle';self.other.write_bytes(b'OTHER PRIVATE INVENTED');self.other.chmod(0o600)
        self.other_metadata=self.other.stat()
        original=os.open
        def no_other(path,*args,**kwargs):
            if path==self.other.name or Path(path)==self.other:
                self.fail('An unrelated bundle was opened')
            return original(path,*args,**kwargs)
        p=patch.object(m.os,'open',side_effect=no_other);p.start();self.addCleanup(p.stop)

    def test_exact_bundle_retained_same_inode_permissions_and_lock(self):
        old=self.bundle.stat();lock=self.lock.stat()
        result=m.retain();target=self.source/m.ARCHIVE/m.BUNDLE
        self.assertEqual(result['code'],'PREVIOUS_INFRASTRUCTURE_BUNDLE_RETAINED')
        self.assertFalse(self.bundle.exists());self.assertEqual(target.read_bytes(),self.payload)
        self.assertEqual(target.stat().st_ino,old.st_ino);self.assertEqual(target.stat().st_nlink,1)
        self.assertEqual(target.stat().st_mode&0o777,0o600)
        self.assertEqual(target.parent.stat().st_mode&0o777,0o700)
        self.assertEqual(self.lock.stat().st_ino,lock.st_ino)
        self.assertEqual(self.other.stat(),self.other_metadata)

    def test_wrong_hash_or_size_never_creates_archive(self):
        for data in (b'X'*len(self.payload),self.payload+b'X',self.payload[:-1]):
            self.bundle.write_bytes(data)
            with self.assertRaises(m.Refused):m.retain()
            self.assertEqual(self.bundle.read_bytes(),data);self.assertFalse((self.source/m.ARCHIVE).exists())

    def test_state_phase_or_foreign_entry_refuses_without_opening_bundle(self):
        for name in ('phase.json','unexpected'):
            path=self.state/name;path.write_text('KEEP')
            with patch.object(m.os,'read',side_effect=AssertionError('read before state refusal')):
                with self.assertRaises(m.Refused):m.retain()
            self.assertFalse((self.source/m.ARCHIVE).exists());path.unlink()

    def test_existing_archive_or_symlink_refused_preserving_both(self):
        path=self.source/m.ARCHIVE
        path.mkdir(mode=0o700);(path/m.BUNDLE).write_bytes(b'KEEP')
        with self.assertRaises(m.Refused):m.retain()
        self.assertEqual((path/m.BUNDLE).read_bytes(),b'KEEP');self.assertTrue(self.bundle.exists())
        (path/m.BUNDLE).unlink();path.rmdir();path.symlink_to(self.state,target_is_directory=True)
        with self.assertRaises(m.Refused):m.retain()
        self.assertTrue(self.bundle.exists())

    def test_bundle_symlink_hardlink_and_public_permissions_refused(self):
        self.bundle.unlink();self.bundle.symlink_to(self.other)
        with self.assertRaises(OSError):m.retain()
        self.bundle.unlink();self.bundle.write_bytes(self.payload);self.bundle.chmod(0o600)
        link=self.root/'extra';os.link(self.bundle,link)
        with self.assertRaises(m.Refused):m.retain()
        link.unlink();self.bundle.chmod(0o644)
        with self.assertRaises(m.Refused):m.retain()
        self.assertFalse((self.source/m.ARCHIVE).exists())

    def test_both_locks_refuse_concurrent_operation(self):
        for path in (self.lock,self.source):
            fd=os.open(path,os.O_RDONLY)
            try:
                fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
                with self.assertRaises(BlockingIOError):m.retain()
            finally:os.close(fd)
            self.assertTrue(self.bundle.exists());self.assertFalse((self.source/m.ARCHIVE).exists())

    def test_wrong_generation_has_no_filesystem_effect(self):
        with patch.object(m.os.path,'realpath',return_value='/wrong'):
            with self.assertRaises(m.Refused):m.retain()
        self.assertTrue(self.bundle.exists());self.assertFalse((self.source/m.ARCHIVE).exists())

    def test_repeat_does_not_overwrite_retained_history_or_new_bundle(self):
        m.retain();retained=self.source/m.ARCHIVE/m.BUNDLE;before=retained.stat()
        self.bundle.write_bytes(b'NEW');self.bundle.chmod(0o600)
        with self.assertRaises(m.Refused):m.retain()
        self.assertEqual(retained.stat(),before);self.assertEqual(self.bundle.read_bytes(),b'NEW')

    def test_rename_failure_retains_original_without_deletion(self):
        with patch.object(m.os,'rename',side_effect=OSError('INVENTED FAILURE')):
            with self.assertRaises(OSError):m.retain()
        self.assertEqual(self.bundle.read_bytes(),self.payload)
        self.assertEqual(list((self.source/m.ARCHIVE).iterdir()),[])


if __name__=='__main__':unittest.main()
