"""Exercise the SQL boundary against disposable PostgreSQL, including END repro."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from coordinator_cases import M


@unittest.skipUnless(os.environ.get('MRJAM_SYNTHETIC_DATABASE_URL') and shutil.which('psql'),
                     'Disposable PostgreSQL fixture required')
class SQLRegression(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.url = os.environ['MRJAM_SYNTHETIC_DATABASE_URL']
        self.step = {'id': 'synthetic_sql_boundary', 'driver': 'sql', 'database': 'synthetic',
                     'compatibility': 'both', 'sql': 'change.sql', 'checks': 'checks.sql', 'fixture': 'fixture.sql'}
        self.path = self.root / 'plan.json'
        self.path.write_text(json.dumps({'version': 1, 'steps': [self.step], 'compatibility_check': 'compatibility.py'}))
        (self.root / 'compatibility.py').write_text('pass\n')
        (self.root / 'fixture.sql').write_text('CREATE TABLE synthetic_qualification_records(id integer PRIMARY KEY);')
        (self.root / 'checks.sql').write_text('SELECT 1/0;')
        self.execute('DROP SCHEMA IF EXISTS mrjam_delivery CASCADE; DROP TABLE IF EXISTS synthetic_qualification_records; '
                     'CREATE TABLE synthetic_qualification_records(id integer PRIMARY KEY);')

    def execute(self, text):
        M.psql('synthetic', text, 'psql', test_url=self.url)

    def count(self):
        return int(subprocess.check_output(['psql', '-X', '-qAt', '--dbname', self.url,
                   '-c', 'SELECT count(*) FROM synthetic_qualification_records'], text=True).strip())

    def test_original_END_rejected_by_load_and_transaction_builder(self):
        (self.root / 'change.sql').write_text('END; INSERT INTO synthetic_qualification_records VALUES (1);')
        with self.assertRaises(ValueError):
            M.load(self.path)
        with self.assertRaises(ValueError):
            M.sql_transaction(self.step, self.root)
        self.assertEqual(self.count(), 0)

    def test_transaction_aliases_and_inline_psql_are_rejected(self):
        for statement in ['END;', 'END WORK;', 'ABORT;', 'COMMIT;', 'ROLLBACK;',
                          'START TRANSACTION;', 'SAVEPOINT synthetic;', 'RELEASE SAVEPOINT synthetic;',
                          "PREPARE TRANSACTION 'synthetic';", 'SET TRANSACTION READ ONLY;', 'SELECT 1; \\gexec']:
            with self.subTest(statement=statement):
                (self.root / 'change.sql').write_text(statement)
                with self.assertRaises(ValueError):
                    M.load(self.path)
                with self.assertRaises(ValueError):
                    M.sql_transaction(self.step, self.root)
        self.assertEqual(self.count(), 0)

    def test_control_words_in_literals_comments_and_DO_remain_legal(self):
        (self.root / 'change.sql').write_text("-- COMMIT END ABORT\nSELECT 'END; ABORT; \\gexec';\n"
                                            "DO $body$ BEGIN PERFORM 'START TRANSACTION'; END $body$;\n"
                                            'INSERT INTO synthetic_qualification_records VALUES (1);')
        M.load(self.path)
        with self.assertRaises(subprocess.CalledProcessError):
            self.execute(M.sql_transaction(self.step, self.root))
        self.assertEqual(self.count(), 0)

    def test_unchecked_SQL_file_change_cannot_bypass_runtime_validation(self):
        (self.root / 'change.sql').write_text('SELECT 1;')
        M.load(self.path)
        (self.root / 'change.sql').write_text('ABORT; INSERT INTO synthetic_qualification_records VALUES (1);')
        with self.assertRaises(ValueError):
            M.sql_transaction(self.step, self.root)
        self.assertEqual(self.count(), 0)

    def test_nested_comment_with_quote_cannot_hide_END_and_persist_data(self):
        # PostgreSQL nests block comments; a single-pass /* ... */ regex does not.
        (self.root / 'change.sql').write_text("/* outer /* inner */ ' */ END;\n"
                                            "INSERT INTO synthetic_qualification_records VALUES (1); SELECT 'ok';")
        try:
            M.load(self.path)
        except ValueError:
            with self.assertRaises(ValueError):
                M.sql_transaction(self.step, self.root)
        else:
            try:
                text = M.sql_transaction(self.step, self.root)
            except ValueError:
                pass
            else:
                with self.assertRaises(subprocess.CalledProcessError):
                    self.execute(text)
        self.assertEqual(self.count(), 0, 'Migration check failed, but END escaped the wrapper and committed a row')

    def assert_no_rows_or_ledger(self):
        self.assertEqual(self.count(), 0)
        missing = subprocess.check_output(['psql', '-X', '-qAt', '--dbname', self.url,
                  '-c', "SELECT to_regnamespace('mrjam_delivery') IS NULL"], text=True).strip()
        self.assertEqual(missing, 't', 'Failed migration left its ledger/schema committed')

    def test_database_boundary_survives_disabled_lexer_in_payload(self):
        for prefix in ['END;', 'COMMIT;', 'ABORT;', "/* outer /* inner */ ' */ END;"]:
            with self.subTest(prefix=prefix):
                (self.root / 'change.sql').write_text(prefix + " INSERT INTO synthetic_qualification_records VALUES (1); SELECT 'ok';")
                (self.root / 'checks.sql').write_text('SELECT 1/0;')
                with patch.object(M, 'validate_sql', return_value=None):
                    M.load(self.path)
                    text = M.sql_transaction(self.step, self.root)
                    with self.assertRaises(subprocess.CalledProcessError):
                        self.execute(text)
                self.assert_no_rows_or_ledger()

    def test_database_boundary_survives_disabled_lexer_in_checks_after_write(self):
        for check in ['END;', 'COMMIT;', 'ABORT;', "/* outer /* inner */ ' */ END; SELECT 'ok';"]:
            with self.subTest(check=check):
                (self.root / 'change.sql').write_text('INSERT INTO synthetic_qualification_records VALUES (1);')
                (self.root / 'checks.sql').write_text(check)
                with patch.object(M, 'validate_sql', return_value=None):
                    M.load(self.path)
                    text = M.sql_transaction(self.step, self.root)
                    with self.assertRaises(subprocess.CalledProcessError):
                        self.execute(text)
                self.assert_no_rows_or_ledger()
