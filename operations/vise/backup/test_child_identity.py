"""A failed child setup must exit before any PostgreSQL command can execute."""
from pathlib import Path
import subprocess
import sys
import unittest


class ChildIdentity(unittest.TestCase):
    def test_each_failed_setup_operation_exits_without_continuing(self):
        code = '''
import sys,types
sys.path.insert(0,sys.argv[1])
import capture as C
stage=int(sys.argv[2])
def fail(): raise PermissionError('invented setup refusal')
def limit(which,value):
    if (stage==73 and which==C.resource.RLIMIT_CORE) or (stage==74 and which==C.resource.RLIMIT_FSIZE): fail()
C.resource.setrlimit=limit
C.os.setgroups=lambda value: fail() if stage==75 else None
C.os.setgid=lambda value: fail() if stage==76 else None
C.os.setuid=lambda value: fail() if stage==77 else None
s=C.Snapshot.__new__(C.Snapshot)
s.postgres=types.SimpleNamespace(pw_gid=999,pw_uid=999)
s.pg_identity()
print('UNSAFE_CONTINUATION')
'''
        for expected in range(73, 78):
            with self.subTest(stage=expected):
                result = subprocess.run([sys.executable, '-I', '-S', '-c', code,
                    str(Path(__file__).resolve().parent), str(expected)],
                    capture_output=True, timeout=10)
                self.assertEqual(result.returncode, expected)
                self.assertEqual(result.stdout, b'')
                self.assertEqual(result.stderr, b'')


if __name__ == '__main__': unittest.main()
