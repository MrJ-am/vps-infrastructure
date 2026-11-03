import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import source_snapshot as S

GIT = str(Path(shutil.which('git')).resolve())
SPEC = importlib.util.spec_from_file_location('tree_gate', '/nix/store/26qr08ambmn7g5dccqbr8q7aqkvcd92f-check_git_tree.py')
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


class NativeSnapshot(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'repo'
        self.repo.mkdir(mode=0o700)
        self.env = {**os.environ, 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
                    'GIT_AUTHOR_NAME': 'Synthetic', 'GIT_AUTHOR_EMAIL': 'synthetic@example.invalid',
                    'GIT_COMMITTER_NAME': 'Synthetic', 'GIT_COMMITTER_EMAIL': 'synthetic@example.invalid'}
        self.git('init', '-q', '-b', 'main')
        self.write('src/main.rs', b'fn main() {}\n')
        self.base = self.commit('base')
        self.write('src/main.rs', b'fn main() { println!("changed"); }\n')
        self.head = self.commit('head')
        self.reader = S.NativeObjects(self.repo / '.git', GIT)

    def git(self, *args):
        return subprocess.check_output([GIT, '-c', 'core.hooksPath=/dev/null', '-C', str(self.repo), *args],
                                       env=self.env, stderr=subprocess.DEVNULL).strip()

    def write(self, path, raw):
        p = self.repo / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(raw)

    def commit(self, message):
        self.git('add', '.')
        self.git('commit', '-qm', message)
        return self.git('rev-parse', 'HEAD').decode()

    def snapshot(self, head=None, selector=lambda p: p.endswith('.rs')):
        return S.snapshot(self.reader, self.base, head or self.head, selector)

    def test_native_commit_tree_and_selected_bytes(self):
        tree, blobs = self.snapshot()
        self.assertEqual(tree['sha'], self.git('rev-parse', self.head+'^{tree}').decode())
        GATE.validate_complete_tree(tree, tree['sha'])
        self.assertEqual(blobs, {'src/main.rs': self.git('show', self.head+':src/main.rs')+b'\n'})

    def test_new_files_above_old_128_limit_are_all_received(self):
        for i in range(137):
            self.write(f'src/file{i:03d}.rs', b'// synthetic\n')
        tree, blobs = self.snapshot(self.commit('137 new files'))
        self.assertEqual(len(blobs), 138)
        GATE.validate_complete_tree(tree, tree['sha'])

    def test_candidate_scripts_are_never_executed(self):
        marker = self.root/'executed'
        self.write('build.sh', ('#!/bin/sh\ntouch '+str(marker)+'\n').encode())
        (self.repo/'build.sh').chmod(0o755)
        _, blobs = self.snapshot(self.commit('script'), lambda _: True)
        self.assertIn('build.sh', blobs)
        self.assertFalse(marker.exists())

    def test_selected_symlink_refused(self):
        (self.repo/'src/link.rs').symlink_to('../../outside')
        with self.assertRaisesRegex(S.Refused, '^SOURCE_LINK_REFUSED$'):
            self.snapshot(self.commit('symlink'))

    def test_lfs_pointer_is_not_an_artifact(self):
        self.write('src/large.rs', b'version https://git-lfs.github.com/spec/v1\noid sha256:'+b'0'*64+b'\nsize 123\n')
        with self.assertRaisesRegex(S.Refused, '^LFS_CONTENT_NOT_RESOLVED$'):
            self.snapshot(self.commit('pointer'))

    def test_unicode_unselected_paths_preserve_complete_tree(self):
        self.write('docs/étude.txt', b'synthetic unselected document')
        tree, blobs = self.snapshot(self.commit('unicode metadata'))
        GATE.validate_complete_tree(tree, tree['sha'])
        self.assertNotIn('docs/étude.txt', blobs)

    def test_gitlinks_are_metadata_not_recursively_checked_out(self):
        self.git('update-index', '--add', '--cacheinfo', '160000,'+self.base+',components/example')
        self.git('commit', '-qm', 'gitlink')
        tree, blobs = self.snapshot(self.git('rev-parse', 'HEAD').decode())
        link = next(x for x in tree['tree'] if x['type']=='commit')
        self.assertEqual(link['sha'], self.base)
        self.assertNotIn('components/example', blobs)
        GATE.validate_complete_tree(tree, tree['sha'])

    def test_foreign_base_is_refused(self):
        self.git('checkout', '--orphan', 'foreign')
        foreign = self.commit('foreign root')
        with self.assertRaisesRegex(S.Refused, '^BASE_NOT_ANCESTOR$'):
            S.ancestry(self.reader, foreign, self.head)

    def test_replacement_objects_cannot_change_source(self):
        self.git('checkout', '-q', self.base)
        self.write('src/main.rs', b'// replacement\n')
        replacement = self.commit('replacement')
        self.git('replace', self.head, replacement)
        _, blobs = self.snapshot()
        self.assertIn(b'changed', blobs['src/main.rs'])

    def test_blob_hash_checked_even_with_untrusted_reader(self):
        native = self.reader
        class Tamper:
            def read(self, kind, oid, limit):
                raw = native.read(kind, oid, limit)
                return raw+b'x' if kind=='blob' else raw
        with self.assertRaisesRegex(S.Refused, '^BLOB_HASH_REFUSED$'):
            S.snapshot(Tamper(), self.base, self.head, lambda _: True)

    def test_limits_do_not_return_partial_success(self):
        with patch.object(S, 'MAX_SELECTED_BYTES', 1):
            with self.assertRaisesRegex(S.Refused, '^OBJECT_SIZE_REFUSED$'):
                self.snapshot()

    def test_ref_injection_missing_object_and_deadline(self):
        for oid in ['HEAD', '--help', self.head+'^{tree}']:
            with self.assertRaises(S.Refused):
                self.reader.read('blob', oid, 1024)
        with self.assertRaisesRegex(S.Refused, '^GIT_OBJECT_UNAVAILABLE$'):
            self.reader.read('blob', '0'*40, 1024)
        self.reader.end = 0
        with self.assertRaisesRegex(S.Refused, '^OBJECT_READ_DEADLINE$'):
            self.snapshot()


if __name__ == '__main__':
    unittest.main()
