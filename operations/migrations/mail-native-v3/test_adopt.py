"""Synthetic mail queues only; no service, relay or installed legacy execution."""
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

MESSAGE = b'From: invented@example.invalid\r\nTo: archive@example.invalid\r\n\r\nInvented\x00opaque\xff\r\n'
DIGEST = hashlib.sha256(MESSAGE).hexdigest()
BUSINESS = 'd' * 64
KEY = 'fermeture:' + 'a' * 64


def mail(*, native=True, hashes=2, key=KEY):
    db = adopt.reference(native=native, hashes=hashes)
    values = (key, MESSAGE, 100, 'attente', 3, 450, None, 'relais_indisponible')
    if hashes >= 1:
        values += (DIGEST,)
    if hashes == 2:
        values += (BUSINESS,)
    db.execute('INSERT INTO courriels VALUES(' + ','.join('?' for _ in values) + ')', values)
    db.commit()
    return db


class Adoption(unittest.TestCase):
    def setUp(self):
        self.mail = mail()
        self.addCleanup(self.mail.close)
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.destination = self.directory / adopt.DESTINATION
        self.pending = self.directory / adopt.PENDING

    def merged(self):
        return adopt.merge(self.mail.serialize())

    def target_rows(self, raw):
        db = adopt.inspect(raw, target=True)
        try:
            return adopt.rows(db)[1]
        finally:
            db.close()

    def test_schema_sources_keep_their_pinned_bytes(self):
        provenance = json.loads((adopt.ROOT / 'schema-provenance.json').read_text())
        for source in provenance['sources']:
            self.assertEqual(hashlib.sha256((adopt.ROOT / 'schemas' / source['schema']).read_bytes()).hexdigest(), source['schema_sha256'])

    def test_each_exact_source_schema_preserves_all_original_values(self):
        for native in (False, True):
            for hashes in (0, 1, 2):
                with self.subTest(native=native, hashes=hashes):
                    db = mail(native=native, hashes=hashes)
                    try:
                        original = db.serialize()
                        self.assertEqual(self.target_rows(adopt.merge(original)),
                                         [(KEY, MESSAGE, 100, 'attente', 3, 450, None,
                                           'relais_indisponible', DIGEST if hashes else None,
                                           None, BUSINESS if hashes == 2 else None)])
                        self.assertEqual(db.serialize(), original)
                    finally:
                        db.close()

    def test_global_and_closure_merge_is_order_independent(self):
        other = mail(key='effacement:' + 'b' * 64)
        try:
            first, second = self.mail.serialize(), other.serialize()
            a, b = adopt.merge(first, second), adopt.merge(second, first)
            self.assertEqual(a, b)
            rows = self.target_rows(a)
            self.assertEqual(len(rows), 2)
            self.assertEqual({r[0] for r in rows}, {KEY, 'effacement:' + 'b' * 64})
            self.assertTrue(all(r[1:] == rows[0][1:] for r in rows))
            self.assertEqual((self.mail.serialize(), other.serialize()), (first, second))
        finally:
            other.close()

    def test_identical_collision_is_deduplicated_even_across_pinned_ddl(self):
        other = mail(native=False)
        try:
            result = adopt.merge(self.mail.serialize(), other.serialize())
            self.assertEqual(self.target_rows(result), self.target_rows(self.merged()))
        finally:
            other.close()

    def test_every_different_preserved_value_refuses_a_collision(self):
        changes = [('message', MESSAGE+b'different'), ('cree', 101),
                   ('etat', 'annule'), ('essais', 4), ('prochain', 451),
                   ('accepte', 500), ('erreur', 'other_synthetic_error'),
                   ('empreinte', None), ('empreinte_metier', None)]
        for column, value in changes:
            with self.subTest(column=column):
                other = mail()
                try:
                    other.execute(f'UPDATE courriels SET {column}=?', (value,))
                    if column == 'message':
                        other.execute('UPDATE courriels SET empreinte=?', (hashlib.sha256(value).hexdigest(),))
                    other.commit()
                    with self.assertRaises(adopt.Refused):
                        adopt.merge(self.mail.serialize(), other.serialize())
                    self.assertFalse(self.destination.exists())
                finally:
                    other.close()

    def test_all_historical_key_shapes_are_kept_without_rewriting_prefixes(self):
        for key in ('fermeture:'+'1'*64, 'effacement:'+'2'*64, 'preavis:invented.thing',
                    'Synthetic-global_key.1:retry', 'a'*160):
            with self.subTest(key=key):
                self.mail.execute('UPDATE courriels SET cle=?', (key,))
                self.mail.commit()
                self.assertEqual(self.target_rows(self.merged())[0][0], key)

    def test_empty_retained_messages_preserve_proofs_and_retry_metadata(self):
        for state in ('accepte_relais', 'annule'):
            self.mail.execute("UPDATE courriels SET message=X'',etat=?,accepte=300", (state,))
            self.mail.commit()
            row = self.target_rows(self.merged())[0]
            self.assertEqual(row, (KEY, b'', 100, state, 3, 450, 300,
                                   'relais_indisponible', DIGEST, None, BUSINESS))

    def test_business_proof_is_never_mapped_to_rust_content_hash(self):
        row = self.target_rows(self.merged())[0]
        self.assertEqual(row[8:], (DIGEST, None, BUSINESS))

    def test_extra_sql_objects_or_target_input_are_refused(self):
        for ddl in ('CREATE VIEW private AS SELECT * FROM courriels',
                    'CREATE TRIGGER injected AFTER INSERT ON courriels BEGIN DELETE FROM courriels; END',
                    'CREATE INDEX unexpected ON courriels(erreur)',
                    'CREATE TABLE private(contents TEXT)',
                    'ALTER TABLE courriels ADD COLUMN unexpected TEXT'):
            with self.subTest(ddl=ddl):
                db = mail()
                try:
                    db.execute(ddl)
                    with self.assertRaises(adopt.Refused):
                        adopt.merge(db.serialize())
                finally:
                    db.close()
        with self.assertRaises(adopt.Refused):
            adopt.merge(self.merged())

    def test_invalid_types_keys_states_dates_sizes_and_hashes_are_refused(self):
        changes = [('cle', None), ('cle', ''), ('cle', 'a'*161), ('cle', 'space key'),
                   ('cle', 'cl\u00e9'), ('cle', 'x\n'), ('etat', 'unknown'),
                   ('message', 'not a blob'), ('message', b'x'*131073),
                   ('empreinte', '0'*64), ('empreinte', 'not-a-hash'),
                   ('empreinte_metier', 'wrong'), ('essais', -1),
                   ('cree', 'not-an-integer'), ('prochain', -1),
                   ('accepte', -1), ('erreur', 'x'*8193)]
        for column, value in changes:
            with self.subTest(column=column):
                self.mail.execute('SAVEPOINT invalid')
                self.mail.execute(f'UPDATE courriels SET {column}=?', (value,))
                with self.assertRaises((adopt.Refused, sqlite3.Error)):
                    self.merged()
                self.mail.execute('ROLLBACK TO invalid')
                self.mail.execute('RELEASE invalid')

    def test_wal_corrupt_truncated_or_too_many_sources_are_refused(self):
        original = self.mail.serialize()
        for raw in (b'not sqlite', original[:99], original[:18]+b'\x02\x02'+original[20:],
                    original[:100]+b'\xff'*(len(original)-100)):
            with self.subTest(length=len(raw)):
                with self.assertRaises((adopt.Refused, sqlite3.Error)):
                    adopt.merge(raw)
        for sources in ((), (original, original, original)):
            with self.assertRaises(adopt.Refused):
                adopt.merge(*sources)

    def test_per_source_and_merged_row_bound_never_truncate(self):
        self.mail.execute('DELETE FROM courriels')
        self.mail.executemany('INSERT INTO courriels(cle,message,cree,etat) VALUES(?,?,?,?)',
                             [(f'item:{n:05}', b'', 1, 'annule') for n in range(10001)])
        self.mail.commit()
        with self.assertRaises(adopt.Refused):
            self.merged()
        self.mail.execute("DELETE FROM courriels WHERE cle='item:10000'")
        self.mail.commit()
        other = mail()
        try:
            with self.assertRaises(adopt.Refused):
                adopt.merge(self.mail.serialize(), other.serialize())
        finally:
            other.close()

    def test_two_empty_exact_snapshots_create_a_valid_empty_queue(self):
        self.mail.execute('DELETE FROM courriels')
        self.mail.commit()
        self.assertEqual(self.target_rows(adopt.merge(self.mail.serialize(), self.mail.serialize())), [])

    def test_cycle_preserves_exact_completion_table_and_every_marker(self):
        self.mail.executescript(adopt.schema('cycle-markers.sql'))
        self.mail.executemany('INSERT INTO effacements_termines VALUES(?)', [('invented-a',), ('invented_B.2',)])
        self.mail.commit()
        before = self.mail.serialize()
        result = adopt.merge(before, profile='cycle')
        db = adopt.inspect(result, target=True, scope='cycle')
        try:
            self.assertEqual(adopt.marker_rows(db, 'cycle'), [('invented-a',), ('invented_B.2',)])
            self.assertEqual(adopt.rows(db)[1][0][1], MESSAGE)
            self.assertEqual(self.mail.serialize(), before)
        finally:
            db.close()

    def test_archive_preserves_closure_steps_without_inventing_intention_date(self):
        self.mail.executescript(adopt.schema('closure-markers.sql'))
        markers = [('invented-a', 201, None), ('invented-b', 202, 203), ('invented-c', None, None)]
        self.mail.executemany('INSERT INTO fermetures VALUES(?,?,?)', markers)
        self.mail.commit()
        other = mail(key='effacement:'+'b'*64)
        try:
            result = adopt.merge(self.mail.serialize(), other.serialize(), profile='archive')
            db = adopt.inspect(result, target=True, scope='archive')
            try:
                self.assertEqual(adopt.marker_rows(db, 'archive'), markers)
                self.assertEqual(len(adopt.rows(db)[1]), 2)
                self.assertEqual([r[1] for r in db.execute('PRAGMA table_info(fermetures)')],
                                 ['sujet', 'outils_effaces', 'terminee'])
            finally:
                db.close()
        finally:
            other.close()

    def test_marker_tables_are_only_accepted_in_their_own_source_scope(self):
        empty = adopt.reference(native=True, hashes=2)
        try:
            for marker in ('cycle', 'closure'):
                db = adopt.reference(native=True, hashes=2, marker=marker)
                try:
                    for scope in ('global', 'mail', 'closure' if marker == 'cycle' else 'cycle'):
                        with self.subTest(marker=marker, scope=scope), self.assertRaises(adopt.Refused):
                            adopt.inspect(db.serialize(), scope=scope)
                    with self.assertRaises(adopt.Refused):
                        adopt.merge(empty.serialize(), db.serialize(), profile='archive')
                finally:
                    db.close()
        finally:
            empty.close()

    def test_marker_schema_types_identifier_and_row_bounds_are_closed(self):
        for value in (None, 'bad identifier', 'x'*65, 'invente\u00e9'):
            db = adopt.reference(native=True, hashes=2, marker='cycle')
            try:
                db.execute('INSERT INTO effacements_termines VALUES(?)', (value,))
                db.commit()
                with self.assertRaises(adopt.Refused):
                    adopt.merge(db.serialize(), profile='cycle')
            finally:
                db.close()
        for value in (-1, 'not-a-date', b'blob'):
            db = adopt.reference(native=True, hashes=2, marker='closure')
            try:
                db.execute('INSERT INTO fermetures VALUES(?,?,NULL)', ('invented-a', value))
                db.commit()
                with self.assertRaises(adopt.Refused):
                    adopt.merge(db.serialize(), self.mail.serialize(), profile='archive')
            finally:
                db.close()
        db = adopt.reference(native=True, hashes=2, marker='cycle')
        try:
            db.executemany('INSERT INTO effacements_termines VALUES(?)', [(f'user-{n}',) for n in range(10001)])
            db.commit()
            with self.assertRaises(adopt.Refused):
                adopt.merge(db.serialize(), profile='cycle')
        finally:
            db.close()

    def test_marker_changes_refuse_republication_even_when_mail_is_identical(self):
        self.mail.executescript(adopt.schema('cycle-markers.sql'))
        self.mail.execute("INSERT INTO effacements_termines VALUES('invented-a')")
        self.mail.commit()
        with patch.object(adopt, 'PROFILE', 'cycle'):
            original = adopt.merge(self.mail.serialize(), profile='cycle')
            adopt.publish(self.directory, original)
            adopt.publish(self.directory, original)
            self.mail.execute("INSERT INTO effacements_termines VALUES('invented-b')")
            self.mail.commit()
            with self.assertRaises(adopt.Refused):
                adopt.publish(self.directory, adopt.merge(self.mail.serialize(), profile='cycle'))
            self.assertEqual(self.destination.read_bytes(), original)

    def test_absence_and_empty_presence_of_marker_table_remain_distinct(self):
        absent = adopt.merge(self.mail.serialize(), profile='cycle')
        self.mail.executescript(adopt.schema('cycle-markers.sql'))
        present = adopt.merge(self.mail.serialize(), profile='cycle')
        with patch.object(adopt, 'PROFILE', 'cycle'):
            self.assertFalse(adopt.equivalent(absent, present))
        for inputs, profile in [((self.mail.serialize(),), 'archive'),
                                ((self.mail.serialize(), self.mail.serialize()), 'cycle'),
                                ((self.mail.serialize(),), 'global')]:
            with self.assertRaises(adopt.Refused):
                adopt.merge(*inputs, profile=profile)

    def test_atomic_private_idempotent_publication_does_not_rewrite(self):
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

    def test_existing_changed_state_is_never_overwritten(self):
        adopt.publish(self.directory, self.merged())
        original = self.destination.read_bytes()
        self.mail.execute('UPDATE courriels SET essais=4')
        self.mail.commit()
        with self.assertRaises(adopt.Refused):
            adopt.publish(self.directory, self.merged())
        self.assertEqual(self.destination.read_bytes(), original)

    def test_crash_before_link_resumes_only_the_verified_pending_image(self):
        result = self.merged()
        with patch.object(adopt.os, 'link', side_effect=OSError('INVENTED_CRASH')):
            with self.assertRaises(OSError):
                adopt.publish(self.directory, result)
        self.assertFalse(self.destination.exists())
        self.assertEqual(self.pending.read_bytes(), result)
        adopt.publish(self.directory, result)
        self.assertEqual(self.destination.read_bytes(), result)
        self.assertFalse(self.pending.exists())

    def test_crash_after_link_resumes_only_the_same_verified_inode(self):
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

    def test_changed_pending_image_and_unrelated_two_link_state_are_refused(self):
        result = self.merged()
        self.pending.write_bytes(result)
        self.pending.chmod(0o600)
        self.mail.execute('UPDATE courriels SET essais=4')
        self.mail.commit()
        with self.assertRaises(adopt.Refused):
            adopt.publish(self.directory, self.merged())
        self.assertFalse(self.destination.exists())
        self.pending.unlink()
        adopt.publish(self.directory, result)
        os.link(self.destination, self.directory / 'unrelated')
        with self.assertRaises(adopt.Refused):
            adopt.publish(self.directory, result)

    def test_exclusive_directory_lock_prevents_concurrent_publication(self):
        fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):
                adopt.publish(self.directory, self.merged())
            self.assertFalse(self.destination.exists())
        finally:
            os.close(fd)

    def test_symlink_hardlink_and_public_permissions_are_refused(self):
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

    def test_fixed_profiles_have_disjoint_inputs_and_destinations(self):
        self.assertEqual(adopt.PROFILES, {
            'cycle': (Path('/run/mrjam-cycle-mail-adoption'), ('mail.sqlite',), Path('/var/lib/mrjam-vision-cycle')),
            'archive': (Path('/run/mrjam-archive-mail-adoption'), ('closure.sqlite', 'global.sqlite'), Path('/var/lib/mrjam-vision-archive')),
        })
        for mode in adopt.PROFILES:
            with patch.object(adopt, 'PROFILE', mode):
                for name in ('../mail.sqlite', '/tmp/arbitrary', 'requests.sqlite', 'other.sqlite'):
                    with self.assertRaises(adopt.Refused):
                        adopt.sealed_input(name)

    def test_cli_is_closed_and_errors_never_echo_input_details(self):
        for args, uid, mode in [(['adopt', 'archive'], 59990, 'cycle'),
                                (['adopt'], 0, 'archive'),
                                (['adopt'], 59990, None),
                                (['adopt'], 59990, 'archive')]:
            error, output = io.StringIO(), io.StringIO()
            with patch.object(adopt.sys, 'argv', args), patch.object(adopt.os, 'geteuid', return_value=uid), \
                    patch.object(adopt, 'PROFILE', mode), \
                    patch.object(adopt, 'sealed_input', side_effect=ValueError('INVENTED_PRIVATE_VALUE')), \
                    contextlib.redirect_stderr(error), contextlib.redirect_stdout(output):
                self.assertEqual(adopt.main(), 1)
            self.assertEqual(output.getvalue(), '')
            self.assertEqual(error.getvalue(), '{"error":"MAIL_ADOPTION_REFUSED"}\n')


if __name__ == '__main__':
    unittest.main()
