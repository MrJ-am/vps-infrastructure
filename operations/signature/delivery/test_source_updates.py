"""Exercise Signature updates through the real shared Git preparation path."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT/'operations/ci/continuous-delivery-v1'), os.environ['SIGNATURE_ASSEMBLY']]
import proposal_prepare as Q
import policy as P

BASE = Path(os.environ['SIGNATURE_PLATFORM_SOURCE'])
POLICY = json.loads(Path(os.environ['SIGNATURE_PLATFORM_POLICY']).read_bytes())
HEAD = next(s['revision'] for s in POLICY['sources'] if s['id']=='signature')
GATE = Path('/nix/store/26qr08ambmn7g5dccqbr8q7aqkvcd92f-check_git_tree.py')
spec = importlib.util.spec_from_file_location('tree_gate', GATE)
G = importlib.util.module_from_spec(spec)
spec.loader.exec_module(G)


class Updates(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.repo = self.root/'objects.git'
        self.git_path = shutil.which('git')
        self.env = {'PATH':'/nonexistent', 'HOME':'/nonexistent',
                    'GIT_CONFIG_NOSYSTEM':'1', 'GIT_CONFIG_GLOBAL':'/dev/null',
                    'GIT_NO_REPLACE_OBJECTS':'1', 'GIT_ALLOW_PROTOCOL':'',
                    'GIT_INDEX_FILE':str(self.root/'index')}
        self.git('init','--bare','--quiet',str(self.repo))
        objects=ROOT/'.local/signature-delivery-20261104.git/objects'
        self.assertTrue(objects.is_dir())
        (self.repo/'objects/info/alternates').write_text(str(objects)+'\n')
        self.git('read-tree',HEAD)

    def git(self,*args,raw=None):
        return subprocess.check_output([self.git_path,'-c','core.hooksPath=/dev/null',
            '--git-dir='+str(self.repo),*args],env=self.env,input=raw,
            stderr=subprocess.DEVNULL).strip().decode()

    def prepare(self):
        tree=self.git('write-tree')
        raw=(f'tree {tree}\nparent {HEAD}\nauthor Synthetic <test@example.invalid> 1793700000 +0000\n'
             'committer Synthetic <test@example.invalid> 1793700000 +0000\n\nSignature fixture\n').encode()
        head=self.git('hash-object','-t','commit','-w','--stdin',raw=raw)
        result=Q.prepare(BASE,Q.sha((BASE/'manifest.json').read_bytes()),POLICY,
            {'signature':{'reader':Q.S.NativeObjects(self.repo,self.git_path),'base':HEAD,'head':head}},
            self.root/'prepared',validator_policy=P,gate=G,gate_path=GATE)
        return head,result

    def test_new_commit_preserves_resources_and_binds_new_revision(self):
        head,result=self.prepare()
        self.assertNotEqual(result['proposal_sha256'],Q.sha((BASE/'manifest.json').read_bytes()))
        self.assertEqual(next(s['revision'] for s in result['policy']['sources'] if s['id']=='signature'),head)
        for source in (BASE/'sources/signature').rglob('*'):
            if source.is_file():
                self.assertEqual(source.read_bytes(),(self.root/'prepared'/source.relative_to(BASE)).read_bytes())
        self.assertFalse(result['deployment_authorized'])

    def test_missing_required_resource_is_refused(self):
        self.git('update-index','--index-info',raw=b'0 '+b'0'*40+b'\tweb/MrJamSignature.woff2\n')
        with self.assertRaisesRegex(P.Refused, 'SIGNATURE_SOURCE_INCOMPLETE'):
            self.prepare()
        self.assertFalse((self.root/'prepared').exists())


if __name__=='__main__':
    unittest.main()
