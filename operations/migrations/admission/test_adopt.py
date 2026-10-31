"""Invented SQLite images only. No production paths or legacy code execution."""
import contextlib
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import adopt

IDENTIFIER = '11111111-2222-4333-8444-555555555555'
OTHER = '66666666-7777-4888-8999-aaaaaaaaaaaa'
MESSAGE = b'From: invented@example.invalid\r\nTo: nobody@example.invalid\r\n\r\nInvented\x00opaque\xff\r\n'


def requests():
    db = adopt.reference()
    db.execute('''INSERT INTO demandes(id,invitation,notice,courriel,pays,age,parent,
        pseudonyme,parental,manuel,verification,accord,cree,expire,verifie_a,
        accord_a,controle_a,methode,reference,source_pays,sujet,nouvel_utilisateur,etat,terminee)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        (IDENTIFIER, 'a'*64, 'synthetic-notice-v1', 'invented@example.invalid',
         'France', 'mineur', 'parent@example.invalid', 'Personne inventée', 1, 1,
         'b'*64, 'c'*64, 100, 1000, 200, 250, 300, 'controle_invente', 'reference_inventee',
         'declare', 'synthetic_subject', 1, 'provisionnee', None))
    db.commit()
    return db


def mail(with_hash=True):
    db = adopt.reference(mail=True, with_hash=with_hash)
    values = (f'admission:{IDENTIFIER}', MESSAGE, 100, 'attente', 2, 350, None, 'relais_indisponible')
    if with_hash:
        values += (hashlib.sha256(MESSAGE).hexdigest(),)
    db.execute('INSERT INTO courriels VALUES(' + ','.join('?' for _ in values) + ')', values)
    db.commit()
    return db


class Adoption(unittest.TestCase):
    def setUp(self):
        self.requests = requests()
        self.mail = mail()
        self.addCleanup(self.requests.close)
        self.addCleanup(self.mail.close)
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.destination = self.directory / adopt.DESTINATION
        self.pending = self.directory / adopt.PENDING

    def merged(self):
        return adopt.merge(self.requests.serialize(), self.mail.serialize())

    def rejected(self):
        with self.assertRaises((adopt.Refused, sqlite3.Error)):
            self.merged()
        self.assertFalse(self.destination.exists())

    def test_schema_sources_keep_their_pinned_bytes(self):
        provenance = json.loads((adopt.ROOT / 'schema-provenance.json').read_text())
        for source in provenance['sources']:
            self.assertEqual(hashlib.sha256((adopt.ROOT / 'schemas' / source['schema']).read_bytes()).hexdigest(), source['schema_sha256'])

    def test_preserves_every_request_proof_and_opaque_mail_byte(self):
        old_requests, old_mail = self.requests.serialize(), self.mail.serialize()
        merged = adopt.inspect(self.merged(), target=True)
        self.addCleanup(merged.close)
        self.assertEqual(adopt.rows(merged, 'demandes'), adopt.rows(self.requests, 'demandes'))
        names, rows = adopt.rows(merged, 'courriels')
        source_names, source_rows = adopt.rows(self.mail, 'courriels')
        self.assertEqual(names, source_names + ['contenu_sha256'])
        self.assertEqual(rows, [row + (None,) for row in source_rows])
        self.assertEqual(self.requests.serialize(), old_requests)
        self.assertEqual(self.mail.serialize(), old_mail)

    def test_old_mail_without_hash_column_does_not_invent_a_hash(self):
        db = mail(with_hash=False)
        try:
            merged = adopt.inspect(adopt.merge(self.requests.serialize(), db.serialize()), target=True)
            try:
                row = merged.execute('SELECT message,empreinte,contenu_sha256 FROM courriels').fetchone()
                self.assertEqual(row, (MESSAGE, None, None))
            finally:
                merged.close()
        finally:
            db.close()

    def test_retained_empty_mail_keeps_old_hash_and_retry_metadata(self):
        self.mail.execute("UPDATE courriels SET cle=?,message=X'',etat='annule'", (f'parent:{OTHER}',))
        self.mail.commit()
        merged = adopt.inspect(self.merged(), target=True)
        try:
            self.assertEqual(merged.execute('SELECT message,empreinte,essais,prochain FROM courriels').fetchone(),
                             (b'', hashlib.sha256(MESSAGE).hexdigest(), 2, 350))
        finally:
            merged.close()

    def test_pending_or_nonempty_orphan_mail_is_refused(self):
        self.mail.execute('UPDATE courriels SET cle=?', (f'parent:{OTHER}',))
        self.rejected()
        self.mail.execute("UPDATE courriels SET message=X'',empreinte=NULL")
        self.rejected()

    def test_extra_schema_cannot_supply_a_trigger_view_or_index(self):
        for ddl in ('CREATE VIEW private AS SELECT * FROM demandes',
                    'CREATE TRIGGER injected AFTER INSERT ON demandes BEGIN DELETE FROM demandes; END',
                    'CREATE INDEX unexpected ON demandes(pays)',
                    'CREATE TABLE private(contents TEXT)'):
            with self.subTest(ddl=ddl):
                db = requests()
                try:
                    db.execute(ddl)
                    with self.assertRaises(adopt.Refused):
                        adopt.merge(db.serialize(), self.mail.serialize())
                finally:
                    db.close()

    def test_unknown_state_or_malformed_proof_is_refused(self):
        for column, value in [('etat', 'invented-unknown-state'), ('id', None),
                              ('invitation', 'wrong'), ('verification', 'wrong'),
                              ('parental', 2), ('cree', -1), ('cree', 'not-an-integer'),
                              ('notice', 'x'*8193)]:
            with self.subTest(column=column, value=str(value)[:30]):
                self.requests.execute('SAVEPOINT invalid')
                self.requests.execute(f'UPDATE demandes SET {column}=?', (value,))
                self.rejected()
                self.requests.execute('ROLLBACK TO invalid')
                self.requests.execute('RELEASE invalid')

    def test_changed_mail_hash_bad_key_and_oversize_are_refused(self):
        for column, value in [('empreinte', '0'*64), ('cle', None), ('cle', 'other:'+IDENTIFIER),
                              ('message', b'x'*131073), ('essais', -1), ('accepte', -1),
                              ('etat', 'unknown'), ('message', 'not-a-blob')]:
            with self.subTest(column=column):
                self.mail.execute('SAVEPOINT invalid')
                self.mail.execute(f'UPDATE courriels SET {column}=?', (value,))
                self.rejected()
                self.mail.execute('ROLLBACK TO invalid')
                self.mail.execute('RELEASE invalid')

    def test_wal_corrupt_or_truncated_input_is_refused(self):
        original = self.requests.serialize()
        for raw in (b'not sqlite', original[:99], original[:18]+b'\x02\x02'+original[20:],
                    original[:100]+b'\xff'*(len(original)-100)):
            with self.subTest(length=len(raw)):
                with self.assertRaises((adopt.Refused, sqlite3.Error)):
                    adopt.merge(raw, self.mail.serialize())

    def test_row_bound_rejects_without_truncation(self):
        self.mail.execute('DELETE FROM courriels')
        self.mail.executemany('INSERT INTO courriels(cle,message,cree,etat) VALUES(?,?,?,?)',
                             [(f'parent:{n:08x}-7777-4888-8999-aaaaaaaaaaaa', b'', 1, 'annule') for n in range(10001)])
        self.rejected()

    def test_atomic_publication_is_private_and_idempotent_without_rewrite(self):
        result = self.merged()
        adopt.publish(self.directory, result)
        first = self.destination.stat()
        self.assertEqual(first.st_mode & 0o777, 0o600)
        self.assertEqual(first.st_nlink, 1)
        self.assertFalse(self.pending.exists())
        self.assertEqual(self.destination.read_bytes(), result)
        adopt.publish(self.directory, result)
        again = self.destination.stat()
        self.assertEqual((first.st_ino, first.st_mtime_ns), (again.st_ino, again.st_mtime_ns))

    def test_existing_different_state_is_never_overwritten(self):
        result = self.merged()
        adopt.publish(self.directory, result)
        original = self.destination.read_bytes()
        self.requests.execute("UPDATE demandes SET notice='different-invented-notice'")
        with self.assertRaises(adopt.Refused):
            adopt.publish(self.directory, self.merged())
        self.assertEqual(self.destination.read_bytes(), original)

    def test_crash_before_publication_resumes_verified_pending_image(self):
        result = self.merged()
        with patch.object(adopt.os, 'link', side_effect=OSError('INVENTED_CRASH')):
            with self.assertRaises(OSError):
                adopt.publish(self.directory, result)
        self.assertFalse(self.destination.exists())
        self.assertEqual(self.pending.read_bytes(), result)
        adopt.publish(self.directory, result)
        self.assertEqual(self.destination.read_bytes(), result)
        self.assertFalse(self.pending.exists())

    def test_crash_after_publication_resumes_only_same_verified_inode(self):
        result = self.merged()
        with patch.object(adopt.os, 'unlink', side_effect=OSError('INVENTED_CRASH')):
            with self.assertRaises(OSError):
                adopt.publish(self.directory, result)
        self.assertEqual(self.destination.stat().st_ino, self.pending.stat().st_ino)
        self.assertEqual(self.destination.stat().st_nlink, 2)
        adopt.publish(self.directory, result)
        self.assertEqual(self.destination.stat().st_nlink, 1)
        self.assertFalse(self.pending.exists())

    def test_partial_pending_image_requires_separate_recovery(self):
        self.pending.write_bytes(b'INVENTED_PARTIAL_WRITE')
        self.pending.chmod(0o600)
        with self.assertRaises(adopt.Refused):
            adopt.publish(self.directory, self.merged())
        self.assertFalse(self.destination.exists())
        self.assertEqual(self.pending.read_bytes(), b'INVENTED_PARTIAL_WRITE')

    def test_concurrent_runtime_directory_lock_prevents_publication(self):
        fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):
                adopt.publish(self.directory, self.merged())
            self.assertFalse(self.destination.exists())
        finally:
            os.close(fd)

    def test_links_and_public_permissions_cannot_be_adopted(self):
        result = self.merged()
        self.directory.chmod(0o750)
        with self.assertRaises(adopt.Refused):
            adopt.publish(self.directory, result)
        self.directory.chmod(0o700)
        referent = self.directory / 'invented-target'
        referent.write_bytes(result)
        referent.chmod(0o600)
        self.destination.symlink_to(referent)
        with self.assertRaises(OSError):
            adopt.publish(self.directory, result)
        self.destination.unlink()
        os.link(referent, self.destination)
        with self.assertRaises(adopt.Refused):
            adopt.publish(self.directory, result)
        self.destination.unlink()
        adopt.publish(self.directory, result)
        self.destination.chmod(0o640)
        with self.assertRaises(adopt.Refused):
            adopt.publish(self.directory, result)

    def test_cli_refuses_arguments_root_and_never_echoes_details(self):
        for args, uid in [(['adopt', 'arbitrary-path'], 59990), (['adopt'], 0), (['adopt'], 59990)]:
            error, output = io.StringIO(), io.StringIO()
            with patch.object(adopt.sys, 'argv', args), patch.object(adopt.os, 'geteuid', return_value=uid), \
                    patch.object(adopt, 'sealed_input', side_effect=ValueError('INVENTED_PRIVATE_VALUE')), \
                    contextlib.redirect_stderr(error), contextlib.redirect_stdout(output):
                self.assertEqual(adopt.main(), 1)
            self.assertEqual(output.getvalue(), '')
            self.assertEqual(error.getvalue(), '{"error":"ADMISSION_ADOPTION_REFUSED"}\n')


if __name__ == '__main__':
    unittest.main()
