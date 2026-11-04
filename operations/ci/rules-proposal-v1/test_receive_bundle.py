"""Real local files; invented bytes and current UID only in this fixture."""
import ast
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import receive_bundle as m


class Receive(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name);self.fd=os.open(self.path,os.O_RDONLY|os.O_DIRECTORY)
        self.addCleanup(os.close,self.fd)
        self.raw=b'invented proposal bundle\n'*5
        for key,value in {'OWNER':(os.getuid(),os.getgid()),'BYTES':len(self.raw),
                          'SHA256':hashlib.sha256(self.raw).hexdigest()}.items():
            p=patch.object(m,key,value);p.start();self.addCleanup(p.stop)

    def write(self,name,raw):
        path=self.path/name;path.write_bytes(raw);path.chmod(0o600);return path

    def test_first_receive_and_retry_retain_inode(self):
        self.assertTrue(m.publish(self.fd,self.raw));p=self.path/m.FINAL;before=p.stat()
        self.assertFalse(m.publish(self.fd,self.raw));after=p.stat()
        self.assertEqual((before.st_ino,before.st_mtime_ns,before.st_ctime_ns),(after.st_ino,after.st_mtime_ns,after.st_ctime_ns))
        self.assertEqual(p.read_bytes(),self.raw);self.assertEqual(after.st_nlink,1)
        self.assertFalse((self.path/m.PENDING).exists())

    def test_partial_matching_pending_resumes_same_inode(self):
        p=self.write(m.PENDING,self.raw[:13]);inode=p.stat().st_ino
        self.assertTrue(m.publish(self.fd,self.raw));self.assertEqual((self.path/m.FINAL).stat().st_ino,inode)

    def test_empty_pending_resumes(self):
        self.write(m.PENDING,b'');self.assertTrue(m.publish(self.fd,self.raw))

    def test_completed_pending_publishes(self):
        self.write(m.PENDING,self.raw);self.assertTrue(m.publish(self.fd,self.raw))

    def test_interrupted_hardlink_publication_recovers(self):
        p=self.write(m.PENDING,self.raw);os.link(p,self.path/m.FINAL)
        inode=p.stat().st_ino;self.assertFalse(m.publish(self.fd,self.raw))
        self.assertEqual((self.path/m.FINAL).stat().st_ino,inode)
        self.assertEqual((self.path/m.FINAL).stat().st_nlink,1)

    def test_wrong_input_does_not_create_files(self):
        for raw in (self.raw+b'x',self.raw[:-1],b'x'*len(self.raw)):
            with self.assertRaises(m.Refused):m.publish(self.fd,raw)
        self.assertEqual(list(self.path.iterdir()),[])

    def test_foreign_pending_untouched(self):
        p=self.write(m.PENDING,b'foreign')
        with self.assertRaises(m.Refused):m.publish(self.fd,self.raw)
        self.assertEqual(p.read_bytes(),b'foreign');self.assertFalse((self.path/m.FINAL).exists())

    def test_different_final_untouched(self):
        p=self.write(m.FINAL,b'x'*len(self.raw))
        with self.assertRaises(m.Refused):m.publish(self.fd,self.raw)
        self.assertEqual(p.read_bytes(),b'x'*len(self.raw))

    def test_symlinks_are_never_followed(self):
        victim=self.write('victim',self.raw)
        for name in (m.FINAL,m.PENDING):
            p=self.path/name;p.symlink_to(victim)
            with self.assertRaises(OSError):m.publish(self.fd,self.raw)
            p.unlink()
        self.assertEqual(victim.read_bytes(),self.raw)

    def test_wrong_mode_owner_and_foreign_hardlink_refuse(self):
        p=self.write(m.FINAL,self.raw);p.chmod(0o644)
        with self.assertRaises(m.Refused):m.publish(self.fd,self.raw)
        p.chmod(0o600)
        with patch.object(m,'OWNER',(-1,-1)):
            with self.assertRaises(m.Refused):m.publish(self.fd,self.raw)
        os.link(p,self.path/'foreign')
        with self.assertRaises(m.Refused):m.publish(self.fd,self.raw)

    def test_separate_matching_pending_is_not_silently_deleted(self):
        self.write(m.FINAL,self.raw);self.write(m.PENDING,self.raw)
        with self.assertRaises(m.Refused):m.publish(self.fd,self.raw)
        self.assertTrue((self.path/m.PENDING).exists())

    def test_fifo_is_refused_without_blocking(self):
        os.mkfifo(self.path/m.PENDING,0o600)
        with self.assertRaises(m.Refused):m.publish(self.fd,self.raw)

    def test_qualified_directory_traversal_ast_identity(self):
        here=Path(__file__).resolve().parent
        def function(path):
            tree=ast.parse(path.read_text())
            n=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='protected_directory')
            if isinstance(n.body[0],ast.Expr) and isinstance(n.body[0].value,ast.Constant):n.body=n.body[1:]
            return ast.dump(n,include_attributes=False)
        self.assertEqual(function(here/'receive_bundle.py'),function(here.parents[1]/'deployment/receive_postrelease_code.py'))


if __name__=='__main__':unittest.main()
