"""Disposable synthetic code cache; real filesystem and flock operations."""
import fcntl,importlib.util,os,sys,tempfile,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('contract',HERE.parent/'authority-v1/contract.py')
C=importlib.util.module_from_spec(spec);sys.modules['contract']=C;spec.loader.exec_module(C)
import admission_collector as K

class Retention(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.fd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY)
        self.lock=K.lock_cache(self.fd)
    def tearDown(self):
        os.close(self.lock);os.close(self.fd);self.temp.cleanup()
    def write(self,name,files=('server','frontend.tar','verification.json','receipt.json')):
        directory=self.root/name;directory.mkdir(mode=0o700)
        for file in files:
            path=directory/file;path.write_bytes(b'invented code fixture');path.chmod(0o400)
        return directory
    def test_sixty_four_successive_results_without_lifetime_limit(self):
        for number in range(64):
            K.reserve_cache_slot(self.fd)
            name=f'{number:064x}';directory=self.write(name)
            os.utime(directory,ns=(number+1,number+1))
            self.assertLessEqual(len(K.recover_cache(self.fd)),16)
        self.assertEqual(sorted(K.recover_cache(self.fd)),[f'{i:064x}' for i in range(48,64)])
    def test_interrupted_receive_and_interrupted_eviction_recover(self):
        self.write('.staging-'+'a'*64,files=('server',))
        self.write('.gc-'+'b'*64,files=('receipt.json',))
        self.write('c'*64)
        self.assertEqual(K.recover_cache(self.fd),['c'*64])
        self.assertEqual(sorted(p.name for p in self.root.iterdir()),['.collection.lock','c'*64])
    def test_crash_after_rename_can_finish_deletion(self):
        self.write('a'*64)
        os.rename(self.root/('a'*64),self.root/('.gc-'+'a'*64))
        K.recover_cache(self.fd)
        self.assertEqual(os.listdir(self.root),['.collection.lock'])
    def test_symlink_does_not_delete_outside_file(self):
        with tempfile.TemporaryDirectory() as external:
            outside=Path(external)/'protected';outside.write_bytes(b'preserve')
            directory=self.write('.gc-'+'a'*64,files=())
            (directory/'server').symlink_to(outside)
            with self.assertRaises(K.Refused):K.recover_cache(self.fd)
            self.assertEqual(outside.read_bytes(),b'preserve')
            self.assertTrue((directory/'server').is_symlink())
    def test_unknown_file_refuses_cleanup_before_any_deletion(self):
        partial=self.write('.staging-'+'a'*64,files=('server',))
        unrelated=self.write('b'*64,files=('unexpected',))
        with self.assertRaises(K.Refused):K.recover_cache(self.fd)
        self.assertTrue((partial/'server').exists());self.assertTrue((unrelated/'unexpected').exists())
    def test_shared_export_lock_prevents_collector_and_eviction(self):
        fcntl.flock(self.lock,fcntl.LOCK_UN)
        reader=os.open(self.root/'.collection.lock',os.O_RDONLY)
        try:
            fcntl.flock(reader,fcntl.LOCK_SH|fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):K.lock_cache(self.fd)
        finally:os.close(reader)
        another=K.lock_cache(self.fd);os.close(another)

if __name__=='__main__':unittest.main()
