import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import build
import prepare
import record


class Components(unittest.TestCase):
    def test_payload_hashes_exclude_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'index.html').write_bytes(b'candidate-site')
            record.record(root, {'schema_version': 1})
            manifest = json.loads((root / 'artifact.json').read_text())
            self.assertEqual(manifest['payload_sha256'], {'index.html': hashlib.sha256(b'candidate-site').hexdigest()})

    def test_final_manifest_replaces_pre_fixup_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'server').write_bytes(b'unstripped')
            record.record(root, {'schema_version': 1})
            (root / 'server').write_bytes(b'stripped-runtime')
            record.record(root, {'schema_version': 1})
            manifest = json.loads((root / 'artifact.json').read_text())
            self.assertEqual(manifest['payload_sha256'], {'server': hashlib.sha256(b'stripped-runtime').hexdigest()})

    def test_frontend_manifest_matches_strict_server_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs, output = root / 'inputs', root / 'output'
            inputs.mkdir()
            pins = json.loads((prepare.HERE / 'pins.json').read_text())
            (inputs / 'manifest.json').write_text(json.dumps({'pins': pins}))
            lock = root / 'toolchains.lock.json'
            lock.write_text('{}')
            for name, style in pins['styles'].items():
                folder = inputs / 'styles' / style
                folder.mkdir(parents=True, exist_ok=True)
                (folder / 'identite.json').write_text(json.dumps({'revision': '4' * 40}))
                (output / name).mkdir(parents=True)
                (output / name / 'index.html').write_text('synthetic site')
            record.finalize('frontends', inputs, output, '2' * 40, lock)
            expected = {'schema_version', 'artifact', 'source_commits', 'style_revision',
                        'input_manifest_sha256', 'toolchains_lock_sha256', 'payload_sha256',
                        'deployment_authorized', 'runtime_qualification'}
            for name in pins['styles']:
                manifest = json.loads((output / name / 'artifact.json').read_text())
                self.assertEqual(set(manifest), expected)
                self.assertEqual(manifest['source_commits']['infrastructure'], '2' * 40)
                self.assertEqual(manifest['input_manifest_sha256'], record.digest(inputs / 'manifest.json'))
                self.assertEqual(manifest['toolchains_lock_sha256'], record.digest(lock))
                self.assertFalse(manifest['deployment_authorized'])
                self.assertEqual(set(manifest['payload_sha256']), {'index.html'})

    def test_vise_retains_its_distinct_manifest_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs, output = root / 'inputs', root / 'output'
            (inputs / 'apps/vise').mkdir(parents=True)
            output.mkdir()
            (inputs / 'manifest.json').write_text(json.dumps({'pins': json.loads((prepare.HERE / 'pins.json').read_text())}))
            for name in ('LICENSE', 'COPYING'):
                (inputs / 'apps/vise' / name).write_text('synthetic license')
            (output / 'server').write_bytes(b'stripped-runtime')
            record.finalize('vise', inputs, output, '', root / 'unused')
            manifest = json.loads((output / 'artifact.json').read_text())
            self.assertEqual(set(manifest), {'schema_version', 'repository', 'revision',
                             'materialization_sha256', 'files_sha256', 'crypto_format', 'production_qualification'})
            self.assertEqual(manifest['files_sha256']['server'], hashlib.sha256(b'stripped-runtime').hexdigest())

    def test_input_tampering_stops_before_build(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'app.js').write_text('original')
            manifest = {'files': prepare.inventory(root), 'pins': {}}
            (root / 'manifest.json').write_text(json.dumps(manifest))
            (root / 'app.js').write_text('altered')
            with self.assertRaisesRegex(ValueError, 'INPUT_CONTENT_MISMATCH'):
                build.build(root, root / 'out', 'frontends', root)
            self.assertFalse((root / 'out').exists())

    def test_link_escape_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'escape').symlink_to('/etc/passwd')
            with self.assertRaisesRegex(ValueError, 'INPUT_LINK'):
                prepare.inventory(root)

    def test_internal_npm_binary_link_supported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'cli.js').write_text('source')
            (root / 'bin').mkdir()
            (root / 'bin/tool').symlink_to('../cli.js')
            self.assertEqual(prepare.inventory(root)['bin/tool'], {'link': '../cli.js'})

    def test_npm_missing_integrity_stops_before_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'package-lock.json').write_text(json.dumps({'packages': {'node_modules/bad': {'resolved': 'https://registry.npmjs.org/bad'}}}))
            with patch('prepare.subprocess.run') as command:
                with self.assertRaisesRegex(ValueError, 'NPM_ORIGIN_OR_INTEGRITY_REFUSED'):
                    prepare.npm(root, root / 'cache')
                command.assert_not_called()

    def test_candidate_local_source_copied_without_freezing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = root / 'interface-log'
            app.mkdir()
            (app / 'pont.js').write_text('candidate change')
            prepare.copy(app, root / 'prepared')
            self.assertEqual((root / 'prepared/pont.js').read_text(), 'candidate change')

    def test_vise_pin_is_served_explicit_migration_revision(self):
        pins = json.loads((prepare.HERE / 'pins.json').read_text())
        lock = json.loads((prepare.HERE.parent.parent / 'vise/sources-adoption-20261101.lock.json').read_text())
        self.assertEqual(pins['applications']['vise'][1], lock['revision'])
        self.assertEqual(pins['applications']['vise'][1], '8c8ef66f943c10cb1397868bd1c5ed1962a97b5c')


if __name__ == '__main__':
    unittest.main()
