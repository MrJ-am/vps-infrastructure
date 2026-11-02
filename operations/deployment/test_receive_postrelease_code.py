"""Real Nix codec, synthetic private metadata; never a VPS/profile mutation."""
import ast
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest import mock

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location('postrelease', HERE / 'receive_postrelease_code.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / 'postrelease-receiver-public-fixture.txt'
            file.write_text('Synthetic public receiver qualification; no deployment.\n')
            cls.path = subprocess.check_output(['nix-store', '--add-fixed', 'sha256', str(file)], text=True).strip()
        cls.archive = subprocess.check_output(['nix-store', '--export', cls.path], stderr=subprocess.DEVNULL)
        info = json.loads(subprocess.check_output(['nix', '--extra-experimental-features', 'nix-command',
                                                   'path-info', '--json', cls.path], stderr=subprocess.DEVNULL))[cls.path]
        cls.release = {'schema_version': 1, 'export_sha256': hashlib.sha256(cls.archive).hexdigest(),
                       'export_bytes': len(cls.archive), 'required_free_bytes': 2 * len(cls.archive) + 1024**3,
                       'artifacts': {cls.path: {'nar_hash': info['narHash'], 'references': sorted(info['references'])}}}

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.state = root / 'state'
        self.status = root / 'status'
        self.work = root / 'work'
        self.store = root / 'isolated-store'
        self.state.mkdir(mode=0o700)
        self.status.mkdir(mode=0o700)
        self.put(self.state / 'transaction.lock', b'')
        self.put(self.state / 'phase.json', json.dumps({'schema_version': 1, 'phase': 'public-writes-open', 'elapsed_seconds': 99}).encode())
        self.put(self.status / 'result.json', json.dumps({'schema_version': 1, 'code': 'CUTOVER_VERIFIED', 'phase': 'public-writes-open'}).encode())
        self.commands = []
        self.command = m.command

    def put(self, path, raw):
        path.write_bytes(raw)
        path.chmod(0o600)

    @contextlib.contextmanager
    def fixture(self, wrong_generation=False, change_before_import=False):
        fstat = os.fstat
        realpath = os.path.realpath
        count = 0
        def ownership(fd):
            meta = fstat(fd)
            class Metadata:
                def __getattr__(self, key):
                    return 0 if key in ('st_uid', 'st_gid') else getattr(meta, key)
            return Metadata()
        def directories(path, create=False):
            target = {m.STATE: self.state, m.RESULT_DIRECTORY: self.status, m.DIRECTORY: self.work}[path]
            if create:
                target.mkdir(mode=0o700, exist_ok=True)
            return os.open(target, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        def resolved(path, *args, **kwargs):
            nonlocal count
            if path in ('/run/current-system', '/nix/var/nix/profiles/system'):
                if path == '/run/current-system':
                    count += 1
                return '/wrong-generation' if wrong_generation or (change_before_import and count >= 2) else m.CURRENT
            return realpath(path, *args, **kwargs)
        def command(args, source=None):
            self.commands.append(args)
            # Real pinned Nix tools, isolated writable store because this local
            # test user is not a trusted root importer of the machine store.
            # The production receiver has no store override or trust bypass.
            return self.command(args[:1] + ['--store', 'local?root=' + str(self.store)] + args[1:], source)
        with mock.patch.object(m.os, 'geteuid', return_value=0), mock.patch.object(m.os, 'getegid', return_value=0), \
             mock.patch.object(m.os, 'uname', return_value=types.SimpleNamespace(nodename='srv1982677')), \
             mock.patch.object(m.os, 'fstat', side_effect=ownership), mock.patch.object(m.os.path, 'realpath', side_effect=resolved), \
             mock.patch.object(m, 'protected_directory', side_effect=directories), mock.patch.object(m, 'command', side_effect=command):
            yield

    def test_real_nix_import_and_exact_metadata_idempotent(self):
        before = (self.state / 'phase.json').read_bytes()
        inode = (self.state / 'transaction.lock').stat().st_ino
        imported_file = self.store / 'nix/store' / Path(self.path).name
        self.assertFalse(imported_file.exists())
        with self.fixture():
            for _ in range(2):
                result = m.deliver(self.release, io.BytesIO(self.archive))
                self.assertEqual(result, {'schema_version': 1, 'code': 'POSTRELEASE_CODE_IMPORTED',
                                         'store_paths': 1, 'application_activation': False, 'systemd_changes': False})
        self.assertEqual([x[1] for x in self.commands], ['--import', '--verify-path', '--extra-experimental-features'] * 2)
        self.assertEqual(before, (self.state / 'phase.json').read_bytes())
        self.assertEqual(inode, (self.state / 'transaction.lock').stat().st_ino)
        self.assertEqual({p.name for p in self.work.iterdir()}, {'export.nar', 'release.json'})
        self.assertEqual(self.archive, (self.work / 'export.nar').read_bytes())
        self.assertTrue(imported_file.is_file())

    def test_wrong_generation_refused_before_delivery_directory(self):
        with self.fixture(wrong_generation=True), self.assertRaises(m.Refused):
            m.deliver(self.release, io.BytesIO(self.archive))
        self.assertFalse(self.work.exists())
        self.assertFalse(self.commands)

    def test_open_and_terminal_result_are_both_required(self):
        for file, bad in ((self.state / 'phase.json', {'schema_version': 1, 'phase': 'held', 'elapsed_seconds': 99}),
                          (self.status / 'result.json', {'schema_version': 1, 'code': 'CUTOVER_REFUSED_PREVIOUS_GENERATION_RESTORED', 'phase': 'previous-generation-restored'})):
            previous = file.read_bytes()
            self.put(file, json.dumps(bad).encode())
            with self.fixture(), self.assertRaises(m.Refused):
                m.deliver(self.release, io.BytesIO(self.archive))
            self.assertFalse(self.work.exists())
            self.put(file, previous)
        self.assertFalse(self.commands)

    def test_historical_transaction_lock_is_respected(self):
        with (self.state / 'transaction.lock').open('r+b') as lock:
            m.fcntl.flock(lock, m.fcntl.LOCK_EX | m.fcntl.LOCK_NB)
            with self.fixture(), self.assertRaises(BlockingIOError):
                m.deliver(self.release, io.BytesIO(self.archive))
        self.assertFalse(self.work.exists())
        self.assertFalse(self.commands)

    def test_second_gate_refuses_before_import(self):
        with self.fixture(change_before_import=True), self.assertRaises(m.Refused):
            m.deliver(self.release, io.BytesIO(self.archive))
        self.assertFalse(self.commands)

    def test_short_extra_and_wrong_digest_stream_never_import(self):
        for raw in (self.archive[:-1], self.archive + b'x', b'x' * len(self.archive)):
            with self.fixture(), self.assertRaises(m.Refused):
                m.deliver(self.release, io.BytesIO(raw))
        self.assertFalse(self.commands)
        self.assertFalse((self.work / 'export.nar').exists())

    def test_foreign_import_path_is_refused_before_verify(self):
        with mock.patch.object(m, 'command') as command, self.assertRaises(m.Refused):
            m.verify_import(self.release, (self.path + '\n/nix/store/' + 'a'*32 + '-foreign\n').encode())
        command.assert_not_called()

    def test_wrong_nar_hash_or_reference_refused(self):
        for changed in ({'narHash': 'sha256-' + 'A'*43 + '=', 'references': []},
                        {'narHash': self.release['artifacts'][self.path]['nar_hash'], 'references': [self.path]}):
            with mock.patch.object(m, 'command', side_effect=[b'', json.dumps({self.path: changed}).encode()]), self.assertRaises(m.Refused):
                m.verify_import(self.release, (self.path + '\n').encode())

    def test_manifest_and_duplicate_json_refused(self):
        for key, value in (('schema_version', True), ('export_bytes', 0), ('required_free_bytes', 1), ('artifacts', {})):
            changed = copy.deepcopy(self.release)
            changed[key] = value
            with self.assertRaises(m.Refused):
                m.validate_release(changed)
        with self.assertRaises(m.Refused):
            m.parse(b'{"schema_version":1,"schema_version":1}')
        changed = copy.deepcopy(self.release)
        changed['unit_store'] = self.path
        with self.assertRaises(m.Refused):
            m.validate_release(changed)

    def test_more_than_128_sealed_paths_are_accepted(self):
        changed = copy.deepcopy(self.release)
        changed['artifacts'] = {'/nix/store/' + str(index).zfill(32) + '-public-fixture':
                                copy.deepcopy(self.release['artifacts'][self.path]) for index in range(137)}
        self.assertEqual(len(m.validate_release(changed)['artifacts']), 137)

    def test_historical_transport_functions_are_ast_identical(self):
        old = ast.parse((HERE / 'deliver_provision.py').read_text())
        new = ast.parse((HERE / 'receive_postrelease_code.py').read_text())
        for name in ('protected_directory', 'receive'):
            a = next(n for n in old.body if isinstance(n, ast.FunctionDef) and n.name == name)
            b = next(n for n in new.body if isinstance(n, ast.FunctionDef) and n.name == name)
            self.assertEqual(ast.dump(a, include_attributes=False), ast.dump(b, include_attributes=False))

    def test_exception_contents_are_not_exported(self):
        output = io.StringIO()
        with mock.patch.object(m.sys, 'argv', ['fixed']), mock.patch.object(m.signal, 'signal'), \
             mock.patch.object(m.signal, 'alarm'), mock.patch.object(m.resource, 'setrlimit'), \
             mock.patch.object(m, 'deliver', side_effect=ValueError('DO_NOT_EXPORT_PRIVATE_ERROR')), \
             contextlib.redirect_stdout(output):
            self.assertEqual(m.main(), 1)
        self.assertEqual(json.loads(output.getvalue()), {'schema_version': 1, 'code': 'POSTRELEASE_CODE_IMPORT_REFUSED'})

    def test_no_unit_symlink_or_profile_mutation_operation_exists(self):
        tree = ast.parse((HERE / 'receive_postrelease_code.py').read_text())
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
        self.assertFalse(any(isinstance(n.func, ast.Attribute) and n.func.attr in ('symlink', 'unlink', 'remove', 'system') for n in calls))
        constants = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and type(n.value) is str}
        self.assertFalse(any(word in value for value in constants for word in ('systemctl', 'daemon-reload', 'switch-to-configuration', 'mrjam-kanidm-worker-provision')))


if __name__ == '__main__':
    unittest.main()
