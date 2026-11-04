import os,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
sys.path.insert(0,'/nix/store/p2494a4mh5nsp77sfzrfd8zhinz34bmp-mrjam-validate/lib')
from build_stage import snapshot_server
from source_policy import Refused

class ArtifactSnapshot(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.job=self.root/'job'
        self.release=self.job/'target/release';self.release.mkdir(parents=True)
        self.binary=self.release/'etp-carnet-server';self.destination=self.root/'server'

    def test_cargo_hardlink_copied_without_alias(self):
        origin=self.release/'deps-output';origin.write_bytes(b'\x7fELFsynthetic')
        os.link(origin,self.binary)
        self.assertEqual(snapshot_server(self.job,self.destination),origin.read_bytes())
        self.assertEqual(self.destination.stat().st_nlink,1)
        origin.write_bytes(b'changed')
        self.assertEqual(self.destination.read_bytes(),b'\x7fELFsynthetic')

    def test_symbolic_link_refused(self):
        origin=self.root/'outside';origin.write_bytes(b'\x7fELFsynthetic')
        self.binary.symlink_to(origin)
        with self.assertRaises(OSError):snapshot_server(self.job,self.destination)
        self.assertFalse(self.destination.exists())

    def test_parent_symbolic_link_refused(self):
        self.release.rmdir();outside=self.root/'outside';outside.mkdir()
        self.release.symlink_to(outside)
        with self.assertRaises(Refused):snapshot_server(self.job,self.destination)

    def test_non_elf_refused(self):
        self.binary.write_bytes(b'not executable')
        with self.assertRaises(Refused):snapshot_server(self.job,self.destination)

if __name__=='__main__':unittest.main()
