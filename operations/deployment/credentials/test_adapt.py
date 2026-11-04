"""Invented credentials only, with no real services or production paths."""
import contextlib
import fcntl
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import adapt

SMTP = {'host':'smtp.protonmail.ch', 'port':587, 'username':'Invented@example.invalid',
        'password':'OnlyInventedToken123456', 'from_address':'invented@example.invalid',
        'starttls_required':True, 'certificate_verification':True}
CYCLE = {'recipient_age':'age1'+'q'*58, 'adresse_exploitant':'archive@example.invalid'}
CLOSURE = b'C'*43+b'\n'
PUBLIC = {'journal_database':'vision_journal_synthetic',
          'age_program':'/nix/store/'+'0'*32+'-age/bin/age'}


def inputs():
    return adapt.encode(SMTP), adapt.encode(CYCLE), CLOSURE, PUBLIC


class Adaptation(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.output = self.directory / adapt.DESTINATION
        self.pending = self.directory / adapt.PENDING

    def test_smtp_values_are_preserved_and_credentials_stay_out_of_public_config(self):
        result = adapt.convert(*inputs())
        self.assertEqual(json.loads(result['smtp.json']), SMTP)
        self.assertEqual(result['recipient'], b'archive@example.invalid\n')
        self.assertEqual(result['closure'], CLOSURE)
        self.assertNotIn('approval', result)
        for suffix in ('', '-initialize'):
            config = json.loads(result['archive'+suffix+'.json'])
            unit = 'mrjam-vision-archive'+suffix+'.service'
            self.assertEqual(config['age_recipient'], CYCLE['recipient_age'])
            self.assertEqual(config['smtp_file'], '/run/credentials/'+unit+'/smtp')
            self.assertEqual(config['recipient_file'], '/run/credentials/'+unit+'/recipient')
            self.assertEqual(config['age_program'], PUBLIC['age_program'])
            self.assertEqual(config['journal_database'], PUBLIC['journal_database'])
            self.assertNotIn(SMTP['password'], result['archive'+suffix+'.json'].decode())

    def test_legacy_hook_whitespace_only_is_removed(self):
        for raw in (CLOSURE[:-1], b' \t\r\n'+CLOSURE+b' \r\n'):
            self.assertEqual(adapt.convert(*inputs()[:2], raw, PUBLIC)['closure'], CLOSURE)
        for raw in (b'C'*42, b'C'*44, b'C'*42+b'.', b'C'*20+b'\n'+b'C'*22,
                    b'\v'+CLOSURE, b'x'*129, b'\xff'+CLOSURE):
            with self.assertRaises((adapt.Refused, UnicodeError)):
                adapt.convert(*inputs()[:2], raw, PUBLIC)

    def test_smtp_transport_cannot_be_weakened_or_redirected(self):
        for field, value in [('host','attacker.invalid'), ('port',25), ('port',587.0),
                             ('starttls_required',False), ('certificate_verification',False),
                             ('starttls_required',1), ('password','too-short'),
                             ('password','A'*129), ('password','Punctuation-'+'a'*20),
                             ('username','different@example.invalid'),
                             ('from_address','bad\r\n@example.invalid'), ('extra','forbidden')]:
            candidate = dict(SMTP); candidate[field] = value
            with self.subTest(field=field), self.assertRaises(adapt.Refused):
                adapt.convert(adapt.encode(candidate), *inputs()[1:])

    def test_json_duplicates_unknown_fields_and_nonstandard_numbers_are_refused(self):
        values = [b'{"x":1,"x":2}', b'{"x":NaN}', b'[]', b'null', b'\xff', b'x'*65537]
        for raw in values:
            with self.assertRaises((adapt.Refused, UnicodeError, ValueError)):
                adapt.strict_json(raw)
        duplicate = inputs()[0].replace(b'{', b'{"port":587,', 1)
        with self.assertRaises(adapt.Refused):
            adapt.convert(duplicate, *inputs()[1:])
        for missing in SMTP:
            candidate = dict(SMTP); del candidate[missing]
            with self.assertRaises(adapt.Refused):
                adapt.convert(adapt.encode(candidate), *inputs()[1:])

    def test_recipient_extraction_is_exact_and_rejects_extra_fields(self):
        for field, value in [('recipient_age','bad'), ('recipient_age','age1'+'Q'*58),
                             ('adresse_exploitant','a@localhost'), ('adresse_exploitant','a@example.invalid\n'),
                             ('secret','must-not-be-copied')]:
            candidate = dict(CYCLE); candidate[field] = value
            with self.assertRaises(adapt.Refused):
                adapt.convert(inputs()[0], adapt.encode(candidate), CLOSURE, PUBLIC)

    def test_public_build_constants_cannot_select_arbitrary_program_or_database(self):
        for field, value in [('age_program','/usr/bin/age'), ('age_program','/nix/store/../bin/age'),
                             ('journal_database','postgres'), ('journal_database','pg_private'),
                             ('journal_database','host=elsewhere'), ('sql','select 1')]:
            candidate = dict(PUBLIC); candidate[field] = value
            with self.assertRaises(adapt.Refused):
                adapt.convert(*inputs()[:3], candidate)

    def test_approval_uses_32_random_bytes_and_is_distinct(self):
        with patch.object(adapt.os, 'urandom', return_value=b'\x01'*32) as rng:
            value = adapt.new_approval(CLOSURE)
            rng.assert_called_once_with(32)
        self.assertTrue(adapt.valid_approval(value, CLOSURE))
        self.assertEqual(len(value), 44)
        with patch.object(adapt.os, 'urandom', return_value=b'\0'*32) as rng:
            with self.assertRaises(adapt.Refused):
                adapt.new_approval(b'A'*43+b'\n')
            self.assertEqual(rng.call_count, 4)

    def test_atomic_generation_is_private_and_idempotent_without_secret_rotation(self):
        expected = adapt.convert(*inputs())
        adapt.publish(self.directory, expected)
        self.assertFalse(self.pending.exists())
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o700)
        self.assertEqual({p.name for p in self.output.iterdir()}, adapt.OUTPUT_NAMES)
        before = {}
        for path in self.output.iterdir():
            meta = path.stat()
            self.assertEqual((meta.st_mode & 0o777, meta.st_nlink), (0o600, 1))
            before[path.name] = (meta.st_ino, meta.st_mtime_ns, path.read_bytes())
        self.assertTrue(adapt.valid_approval(before['approval'][2], CLOSURE))
        with patch.object(adapt.os, 'urandom', side_effect=AssertionError('NO_ROTATION')):
            adapt.publish(self.directory, expected)
        for name, original in before.items():
            path = self.output/name
            self.assertEqual((path.stat().st_ino, path.stat().st_mtime_ns, path.read_bytes()), original)

    def test_existing_different_generation_is_never_overwritten(self):
        expected = adapt.convert(*inputs())
        adapt.publish(self.directory, expected)
        before = {p.name:p.read_bytes() for p in self.output.iterdir()}
        changed = dict(expected); changed['recipient'] = b'other@example.invalid\n'
        with self.assertRaises(adapt.Refused):
            adapt.publish(self.directory, changed)
        self.assertEqual({p.name:p.read_bytes() for p in self.output.iterdir()}, before)

    def test_crash_before_publication_reuses_completed_private_generation(self):
        expected = adapt.convert(*inputs())
        with patch.object(adapt.os, 'rename', side_effect=OSError('INVENTED_CRASH')):
            with self.assertRaises(OSError):
                adapt.publish(self.directory, expected)
        approval = (self.pending/'approval').read_bytes()
        self.assertFalse(self.output.exists())
        with patch.object(adapt.os, 'urandom', side_effect=AssertionError('NO_ROTATION')):
            adapt.publish(self.directory, expected)
        self.assertEqual((self.output/'approval').read_bytes(), approval)

    def test_interruption_between_files_preserves_approval_and_fills_missing_files(self):
        expected = adapt.convert(*inputs())
        self.pending.mkdir(mode=0o700)
        approval = adapt.new_approval(CLOSURE)
        (self.pending/'approval').write_bytes(approval)
        (self.pending/'approval').chmod(0o600)
        with patch.object(adapt.os, 'urandom', side_effect=AssertionError('NO_ROTATION')):
            adapt.publish(self.directory, expected)
        self.assertEqual((self.output/'approval').read_bytes(), approval)

    def test_partial_file_or_unknown_pending_file_is_refused_without_replacement(self):
        expected = adapt.convert(*inputs())
        self.pending.mkdir(mode=0o700)
        bad = self.pending/'smtp.json'
        bad.write_bytes(b'PARTIAL_SYNTHETIC_WRITE'); bad.chmod(0o600)
        with self.assertRaises(adapt.Refused):
            adapt.publish(self.directory, expected)
        self.assertFalse(self.output.exists())
        self.assertEqual(bad.read_bytes(), b'PARTIAL_SYNTHETIC_WRITE')
        bad.unlink()
        bad = self.pending/'unknown'
        bad.write_bytes(b'unknown'); bad.chmod(0o600)
        with self.assertRaises(adapt.Refused):
            adapt.publish(self.directory, expected)

    def test_directory_lock_prevents_concurrent_generation(self):
        fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):
                adapt.publish(self.directory, adapt.convert(*inputs()))
        finally:
            os.close(fd)
        self.assertFalse(self.output.exists())

    def test_public_permissions_symlink_and_hardlink_are_refused(self):
        expected = adapt.convert(*inputs())
        self.directory.chmod(0o750)
        with self.assertRaises(adapt.Refused):
            adapt.publish(self.directory, expected)
        self.directory.chmod(0o700)
        self.pending.symlink_to(self.directory)
        with self.assertRaises(OSError):
            adapt.publish(self.directory, expected)
        self.pending.unlink()
        adapt.publish(self.directory, expected)
        os.link(self.output/'approval', self.directory/'other-link')
        with self.assertRaises(adapt.Refused):
            adapt.publish(self.directory, expected)
        (self.directory/'other-link').unlink()
        (self.output/'approval').chmod(0o640)
        with self.assertRaises(adapt.Refused):
            adapt.publish(self.directory, expected)

    def test_parent_symlink_is_never_followed(self):
        real = self.directory/'real'; real.mkdir(mode=0o700)
        child = real/'child'; child.mkdir(mode=0o700)
        (self.directory/'link').symlink_to(real)
        with self.assertRaises(OSError):
            adapt.open_directory(self.directory/'link'/'child')

    def test_mutable_source_fails_even_with_sealed_permission_bits(self):
        path = self.directory/'proton-smtp.json'
        path.write_bytes(inputs()[0]); path.chmod(0o440)
        fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            with self.assertRaises(adapt.Refused):
                adapt.read_file(fd, path.name, 65536, sealed=True)
        finally:
            os.close(fd)

    def test_cli_refuses_arguments_unprivileged_uid_and_redacts_all_errors(self):
        for args, uid in [(['adapt','path'],0), (['adapt'],59990), (['adapt'],0)]:
            out, err = io.StringIO(), io.StringIO()
            with patch.object(adapt.sys, 'argv', args), patch.object(adapt.os, 'geteuid', return_value=uid), \
                    patch.object(adapt, 'sealed_inputs', side_effect=ValueError('INVENTED_PRIVATE_VALUE')), \
                    patch.object(adapt.Path, 'read_bytes', return_value=adapt.encode(PUBLIC)), \
                    contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                self.assertEqual(adapt.main(), 1)
            self.assertEqual(out.getvalue(), '')
            self.assertEqual(err.getvalue(), '{"error":"CREDENTIAL_ADAPTATION_REFUSED"}\n')


if __name__ == '__main__':
    unittest.main()
