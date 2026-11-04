import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
for name, filename in [('github_app_auth', 'github-app-receive.py'),
                       ('github_proposals', 'github-proposals.py')]:
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
import source_fetch as F

GIT = shutil.which('git')


class Transport(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.remote = self.root / 'remote.git'
        self.env = {'PATH': '/nonexistent', 'HOME': '/nonexistent',
                    'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
                    'GIT_AUTHOR_NAME': 'Fixture', 'GIT_AUTHOR_EMAIL': 'fixture@example.invalid',
                    'GIT_COMMITTER_NAME': 'Fixture', 'GIT_COMMITTER_EMAIL': 'fixture@example.invalid'}
        self.command('init', '--bare', '--quiet', str(self.remote))
        tree = self.command('--git-dir=' + str(self.remote), 'mktree', data=b'')
        base = self.commit(tree)
        head = self.commit(tree, base)
        self.command('--git-dir=' + str(self.remote), 'update-ref', 'refs/heads/main', base)
        self.command('--git-dir=' + str(self.remote), 'update-ref', 'refs/pull/7/head', head)
        self.proposal = {'repository': 'vision', 'repository_id': F.P.REPOSITORIES['vision'],
                         'number': 7, 'draft': False, 'base': base, 'head': head,
                         'branch': 'unused-untrusted-branch'}
        self.stage = self.root / 'stage'
        self.stage.mkdir(mode=0o700)
        self.calls = []

    def tearDown(self):
        self.temp.cleanup()

    def command(self, *args, data=None):
        return subprocess.check_output([GIT, *args], input=data, env=self.env,
                                       stderr=subprocess.DEVNULL).decode().strip()

    def commit(self, tree, parent=None):
        return self.command('--git-dir=' + str(self.remote), 'commit-tree', tree,
                            *(['-p', parent] if parent else []), data=b'fixture\n')

    def transport(self, args, env):
        self.calls.append(args)
        self.assertNotIn('test-token', ' '.join(args))
        self.assertEqual(env['GIT_ALLOW_PROTOCOL'], 'https')
        if 'fetch' in args:
            position = args.index('https://github.com/MrJ-am/vision.git')
            # The test replaces only the network transport; Git and its object
            # database, refs and subsequent hash/ancestry checks are real.
            args = args[:position] + [str(self.remote)] + args[position + 1:]
            env = dict(env, GIT_ALLOW_PROTOCOL='file')
            args = [args[0], '-c', 'protocol.file.allow=always', *args[1:]]
        F.execute(args, env)

    def test_real_git_objects_and_fixed_refs(self):
        reader = F.fetch(self.stage, GIT, self.proposal, 'test-token', self.transport)
        self.assertEqual(F.S.commit(reader, self.proposal['head'])[1], [self.proposal['base']])
        config = (self.stage / 'objects.git/config').read_text()
        self.assertNotIn('test-token', config)
        self.assertNotIn('Authorization', config)
        self.assertFalse((self.stage / 'objects.git/FETCH_HEAD').exists())
        self.assertIn('+refs/pull/7/head:refs/intake/head', self.calls[-1])

    def test_moving_head_refused(self):
        self.proposal['head'] = 'a' * 40
        with self.assertRaisesRegex(F.S.Refused, 'PROPOSAL_MOVED_DURING_FETCH'):
            F.fetch(self.stage, GIT, self.proposal, 'test-token', self.transport)

    def test_unrelated_history_refused(self):
        tree = self.command('--git-dir=' + str(self.remote), 'mktree', data=b'')
        head = self.command('--git-dir=' + str(self.remote), 'commit-tree', tree, data=b'unrelated\n')
        self.command('--git-dir=' + str(self.remote), 'update-ref', 'refs/pull/7/head', head)
        self.proposal['head'] = head
        with self.assertRaisesRegex(F.S.Refused, 'BASE_NOT_ANCESTOR'):
            F.fetch(self.stage, GIT, self.proposal, 'test-token', self.transport)

    def test_draft_or_foreign_repo_never_fetches(self):
        for update in [{'draft': True}, {'repository_id': 1}, {'number': True}]:
            with self.assertRaises(F.S.Refused):
                F.fetch(self.stage, GIT, dict(self.proposal, **update), 'test-token', self.transport)
        self.assertEqual(self.calls, [])

    def test_nonempty_and_link_directory_refused(self):
        (self.stage / 'occupied').touch()
        with self.assertRaises(F.S.Refused):
            F.fetch(self.stage, GIT, self.proposal, 'test-token', self.transport)
        link = self.root / 'link'
        link.symlink_to(self.stage)
        with self.assertRaises(F.S.Refused):
            F.fetch(link, GIT, self.proposal, 'test-token', self.transport)
        self.assertEqual(self.calls, [])

    def receive_fixture(self, changed=False):
        methods = []
        observations = []
        def api(path, token, method='GET', body=None):
            methods.append(method)
            if method == 'POST':
                self.assertEqual(body['repository_ids'], [F.P.REPOSITORIES['vision']])
                self.assertEqual(body['permissions'], F.P.READ_PERMISSIONS)
                return 201, {'token': 'test-token', 'permissions': F.P.READ_PERMISSIONS}
            if method == 'DELETE':
                return 204, None
            observations.append(path)
            repo = {'id': self.proposal['repository_id'], 'full_name': 'MrJ-am/vision'}
            return 200, {'number': 7, 'state': 'open', 'draft': False,
                         'base': {'repo': repo, 'ref': 'main', 'sha': self.proposal['base']},
                         'head': {'repo': repo, 'ref': self.proposal['branch'],
                                  'sha': 'b' * 40 if changed and len(observations) == 2 else self.proposal['head']}}
        credentials = {'app_id': F.P.APP_ID, 'owner_id': 12571490, 'slug': 'synthetic',
                       'private_key': 'A' * 1500, 'permissions': F.P.A.PERMISSIONS}
        try:
            with patch.object(F.P.A, 'jwt', return_value='synthetic-jwt'):
                result = F.receive(self.stage, GIT, self.proposal, credentials, api, self.transport)
                self.assertEqual(F.S.commit(result, self.proposal['head'])[1], [self.proposal['base']])
        finally:
            self.assertEqual(methods, ['POST', 'GET', 'GET', 'DELETE'])

    def test_read_only_scoped_token_revoked_after_two_observations(self):
        self.receive_fixture()

    def test_api_move_after_fetch_refused_and_token_revoked(self):
        with self.assertRaisesRegex(F.S.Refused, 'PROPOSAL_OBSERVATION_CHANGED'):
            self.receive_fixture(changed=True)


if __name__ == '__main__':
    unittest.main()
