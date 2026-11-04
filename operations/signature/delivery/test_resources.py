"""Real Git fixtures: source binding, link refusal and stale generated metadata."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'ci/continuous-delivery-v1'))
import source_snapshot as S
import resources as R


class Capture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git = shutil.which('git')
        self.environment = dict(os.environ, GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_NOSYSTEM='1',
                                GIT_AUTHOR_NAME='Fixture', GIT_AUTHOR_EMAIL='fixture@example.invalid',
                                GIT_COMMITTER_NAME='Fixture', GIT_COMMITTER_EMAIL='fixture@example.invalid')
        self.command('init', '-q')
        for name in R.INPUTS:
            p = self.root/name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(('Synthetic '+name+'\n').encode())
        geometry = {field: hashlib.sha256((self.root/name).read_bytes()).hexdigest()
                    for field, name in [('source_sha256','mrjam.sty'),
                                        ('font_sha256','fonts/Parisienne-Regular.ttf'),
                                        ('svg_sha256','artwork/Echologo.svg')]}
        (self.root/'web/geometry.json').write_text(json.dumps(geometry))
        self.commit()

    def command(self, *args):
        return subprocess.check_output([self.git, '-c', 'core.hooksPath=/dev/null', *args],
                                       cwd=self.root, env=self.environment, stderr=subprocess.DEVNULL)

    def commit(self):
        self.command('add', '-A')
        self.command('commit', '-qm', 'Fixture')
        self.head = self.command('rev-parse', 'HEAD').decode().strip()

    def capture(self):
        return R.capture(S.NativeObjects(self.root/'.git', self.git), self.head)

    def test_exact_resources_and_commit_without_running_candidate(self):
        script = self.root/'tools/build-web.py'
        script.parent.mkdir()
        script.write_text("raise RuntimeError('candidate must not run')\n")
        self.commit()
        manifest, resources = self.capture()
        self.assertEqual(manifest['revision'], self.head)
        self.assertFalse(manifest['deployment_authorized'])
        self.assertEqual(set(resources), set(R.RESOURCES))
        self.assertEqual(set(manifest['inputs']), R.INPUTS)
        for name, origin in R.RESOURCES.items():
            self.assertEqual(resources[name], (self.root/origin).read_bytes())

    def test_missing_licence_is_refused(self):
        (self.root/'fonts/Parisienne-OFL.txt').unlink()
        self.commit()
        with self.assertRaisesRegex(S.Refused, 'SIGNATURE_INPUT_MISSING'):
            self.capture()

    def test_symlink_is_refused(self):
        p = self.root/'web/MrJamSignature.woff2'
        p.unlink()
        p.symlink_to('/etc/passwd')
        self.commit()
        with self.assertRaisesRegex(S.Refused, 'SIGNATURE_INPUT_MODE_REFUSED'):
            self.capture()

    def test_executable_resource_is_refused(self):
        (self.root/'web/signature.css').chmod(0o755)
        self.commit()
        with self.assertRaisesRegex(S.Refused, 'SIGNATURE_INPUT_MODE_REFUSED'):
            self.capture()

    def test_lfs_pointer_is_refused(self):
        (self.root/'web/EchoPoint.woff2').write_bytes(b'version https://git-lfs.github.com/spec/v1\n')
        self.commit()
        with self.assertRaisesRegex(S.Refused, 'LFS_CONTENT_NOT_RESOLVED'):
            self.capture()

    def test_changed_tex_with_old_geometry_is_refused(self):
        (self.root/'mrjam.sty').write_bytes(b'new composition')
        self.commit()
        with self.assertRaisesRegex(S.Refused, 'SIGNATURE_GEOMETRY_STALE'):
            self.capture()

    def test_invalid_geometry_is_refused(self):
        (self.root/'web/geometry.json').write_bytes(b'[]')
        self.commit()
        with self.assertRaisesRegex(S.Refused, 'SIGNATURE_GEOMETRY_REFUSED'):
            self.capture()

    def test_uncommitted_bytes_do_not_replace_verified_git_objects(self):
        before = self.capture()
        (self.root/'web/signature.css').write_bytes(b'not committed')
        self.assertEqual(self.capture(), before)


if __name__ == '__main__':
    unittest.main()
