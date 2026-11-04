import contextlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('probe',Path(__file__).with_name('builtin_probe.py'))
B=importlib.util.module_from_spec(spec);spec.loader.exec_module(B)


class ProjectionTests(unittest.TestCase):
    def fixture(self,edit=None):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        path=Path(temporary.name)/'kanidm.db'
        with contextlib.closing(sqlite3.connect(path)) as connection,connection:
            connection.execute('CREATE TABLE idx_eq_uuid(key TEXT PRIMARY KEY,idl BLOB)')
            connection.execute('CREATE TABLE id2entry(id INTEGER PRIMARY KEY,data BLOB)')
            for number,(name,uid) in enumerate(B.BUILTINS.items(),1):
                attrs={'uuid':{'UU':[uid]},'name':{'N8':[name]},'class':{'I8':['object','account','service_account']},
                       'account_expire':{'DT':['2000-01-01T00:00:00Z']},'primary_credential':{'SECRET':'INVENTED_PRIVATE_VALUE'}}
                if edit and number==1:edit(attrs)
                connection.execute('INSERT INTO idx_eq_uuid VALUES (?,?)',(uid,json.dumps({'t':{'s':[number]}}).encode()))
                connection.execute('INSERT INTO id2entry VALUES (?,?)',(number,json.dumps({'ent':{'V3':{'attrs':attrs}}}).encode()))
        return path

    def test_expired_builtin_without_person_or_passkeys_is_eligible(self):
        value=B.observe(self.fixture())
        self.assertTrue(value['both_eligible']);self.assertNotIn('INVENTED_PRIVATE_VALUE',json.dumps(value))

    def test_active_account_is_ineligible(self):
        value=B.observe(self.fixture(lambda attrs:attrs.pop('account_expire')))
        self.assertFalse(value['both_eligible']);self.assertFalse(value['builtin_states']['admin']['disabled'])

    def test_both_passkey_types_are_ineligible_even_with_empty_payload(self):
        for field in ('passkeys','attested_passkeys'):
            with self.subTest(field=field):
                value=B.observe(self.fixture(lambda attrs:attrs.update({field:{}})))
                self.assertFalse(value['both_eligible'])

    def test_person_conversion_refuses_recovery(self):
        value=B.observe(self.fixture(lambda attrs:attrs['class'].update({'I8':['object','account','person']})))
        self.assertFalse(value['both_eligible'])

    def test_uuid_name_or_schema_mismatch_is_closed(self):
        for edit in (lambda attrs:attrs['name'].update({'N8':['invented-person']}),
                     lambda attrs:attrs['uuid'].update({'UU':['ffffffff-ffff-ffff-ffff-ffffffffffff']}),
                     lambda attrs:attrs['account_expire'].update({'DT':['invalid']})):
            with self.assertRaises(Exception):B.observe(self.fixture(edit))

    def test_only_exact_index_lookups_and_projections_execute(self):
        path=self.fixture();connect=sqlite3.connect;statements=[]
        def observed(*args,**kwargs):
            self.assertTrue(args[0].endswith('?mode=ro'));self.assertTrue(kwargs['uri'])
            connection=connect(*args,**kwargs);connection.set_trace_callback(statements.append);return connection
        with patch.object(B.sqlite3,'connect',observed):B.observe(path)
        self.assertEqual(len(statements),7)
        self.assertEqual(statements[:3],['PRAGMA query_only=ON','PRAGMA trusted_schema=OFF','BEGIN'])
        self.assertEqual(sum('FROM idx_eq_uuid WHERE key=' in statement for statement in statements),2)
        self.assertEqual(sum('FROM id2entry WHERE id=' in statement for statement in statements),2)
        self.assertFalse(any('primary_credential' in statement or 'SELECT data' in statement for statement in statements))


if __name__=='__main__':unittest.main()
