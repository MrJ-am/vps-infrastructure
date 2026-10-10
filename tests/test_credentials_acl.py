"""ACL réellement accordées à un uid, sans lecture permise aux autres."""
import importlib.util
import os
from pathlib import Path
import stat
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'services/mrjam-courriel/courriel.py'
s=importlib.util.spec_from_file_location('courriel_acl',SOURCE)
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)


def acl(entries):
    return struct.pack('<I',2)+b''.join(struct.pack('<HHI',*e) for e in entries)


BASE=[(1,4,0xffffffff),(2,4,65534),(4,0,0xffffffff),(16,4,0xffffffff),(32,0,0xffffffff)]


class ACLPrive(unittest.TestCase):
    def test_acl_exacte_et_tout_autre_acces_refuse(self):
        self.assertTrue(m.acl_lecture_individuelle(acl(BASE),65534))
        for mauvais in [BASE+[(2,4,65533)],[(1,4,0xffffffff),(2,4,65534),(4,4,0xffffffff),(16,4,0xffffffff),(32,0,0xffffffff)],
                BASE[:-1]+[(32,4,0xffffffff)],BASE[:1]+[(2,6,65534)]+BASE[2:]]:
            self.assertFalse(m.acl_lecture_individuelle(acl(mauvais),65534))
        self.assertFalse(m.acl_lecture_individuelle(acl(BASE),65533))
        self.assertFalse(m.acl_lecture_individuelle(b'\x00'*44,65534))

    @unittest.skipUnless(os.geteuid()==0,'ACL native sous root en qualification')
    def test_lecture_native_uid_et_refus_groupe_ou_autre_uid(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);d.chmod(0o755)
            source=d/'courriel.py';source.write_bytes(SOURCE.read_bytes());source.chmod(0o444)
            p=d/'credential';p.write_text('{"synthetique":true}');p.chmod(0o400)
            os.setxattr(p,'system.posix_acl_access',acl(BASE))
            self.assertEqual(stat.S_IMODE(p.stat().st_mode),0o440)
            code="import importlib.util,sys;s=importlib.util.spec_from_file_location('c',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);assert m.lire_prive(sys.argv[2])=={'synthetique':True}"
            def lancer(uid):
                def sans_privilege():os.setgroups([]);os.setgid(uid);os.setuid(uid)
                return subprocess.run([sys.executable,'-c',code,str(source),str(p)],preexec_fn=sans_privilege,
                    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),capture_output=True)
            self.assertEqual(lancer(65534).returncode,0)
            self.assertNotEqual(lancer(65533).returncode,0)
            os.setxattr(p,'system.posix_acl_access',acl(BASE[:1]+[(2,4,65533)]+BASE[1:]))
            self.assertNotEqual(lancer(65534).returncode,0)
            os.removexattr(p,'system.posix_acl_access');os.chown(p,0,65534);p.chmod(0o440)
            self.assertNotEqual(lancer(65534).returncode,0)

    def test_fichier_partage_ou_trop_grand_refuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'secret';p.write_text('a'*43);p.chmod(0o600)
            self.assertEqual(m.lire_secret_prive(p),'a'*43)
            os.link(p,Path(tmp)/'copie')
            with self.assertRaises(ValueError):m.lire_secret_prive(p)
            (Path(tmp)/'copie').unlink();p.write_text('a'*129)
            with self.assertRaises(ValueError):m.lire_secret_prive(p)


if __name__=='__main__':unittest.main()
