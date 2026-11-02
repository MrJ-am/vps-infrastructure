"""Real PostgreSQL, exact historical bootstrap and exact compiled SQL predicates.

No VPS access. This complements (not replaces) the real ELF/systemd fixture.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import unittest

BASE=Path(__file__).resolve().parent
ROOT=BASE.parent.parent
spec=importlib.util.spec_from_file_location('closure_test',BASE/'test_preflight_closure_catalog.py')
support=importlib.util.module_from_spec(spec);spec.loader.exec_module(support)
SOURCE=Path('/nix/store/l7ckaann5dkj10bincrx635nsxkxhd01-source')
PLATFORM=ROOT/'.local/mrjam-plateforme-identity'
ROLES=('vision_journal_writer','vision_journal_archiviste','vision_journal_rejeu','vision_journal_fermeture')

def exact_queries():
    archive=(SOURCE/'src/workers/archive.rs').read_text()
    writer=(SOURCE/'src/journal_postgres.rs').read_text()
    runtime=(PLATFORM/'crates/server/src/database.rs').read_text()
    if hashlib.sha256(archive.encode()).hexdigest()!='7465396da0f9be09b93ca60e41278f4e483cbc96b1a9aec9610c915783ce17e7':raise AssertionError()
    if hashlib.sha256(writer.encode()).hexdigest()!='246bc590ec6139e581a5d80465f3b0a95dc22d4bfa37c5b1ef86408c26b6b634':raise AssertionError()
    lock=json.loads((ROOT/'operations/builds/sources-runtime-20261031.lock.json').read_text())
    if hashlib.sha256(runtime.encode()).hexdigest()!=lock['sources']['platform']['files']['crates/server/src/database.rs']:raise AssertionError()
    query=re.search(r'query_scalar\(r#"(.*?)"#\)',archive,re.S).group(1)
    result={}
    for role,name in (('vision_journal_archiviste','ARCHIVISTE'),('vision_journal_rejeu','REJEU'),('vision_journal_fermeture','FERMETURE')):
        signatures=re.findall(r'"([^"]+)"',re.search(r'const '+name+r': &\[&str\] = &\[(.*?)\];',archive,re.S).group(1))
        result[role]=query.replace('$1','ARRAY['+','.join("'"+x+"'" for x in signatures)+']')
    result['vision_journal_writer']=re.search(r'const PRECONDITIONS: &str = r#"(.*?)"#;',writer,re.S).group(1)
    result['runtime_writer']=re.search(r'let safe:bool=sqlx::query_scalar\("(.*?)"\)',runtime,re.S).group(1).replace('$1',"'public'")
    return result

class NativeJournal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cluster=support.NativeCatalog
        cls.cluster.setUpClass()
        cls.queries=exact_queries()
        for db,name in (('postgres','01-roles.sql'),('postgres','02-database.sql'),('vision_journal','03-schema.psql')):
            result=cls.file(BASE/'journal-bootstrap/bootstrap-journal'/name,db)
            if result.returncode:raise AssertionError('EXACT_BOOTSTRAP_FAILED')

    @classmethod
    def tearDownClass(cls):cls.cluster.tearDownClass()

    @classmethod
    def file(cls,path,database):
        return subprocess.run([str(support.PG/'psql'),'-X','-w','-qAt','-h',str(cls.cluster.root),'-d',database,
            '-v','ON_ERROR_STOP=1','-f',str(path)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)

    def sql(self,query):return self.cluster.sql(query,'vision_journal').strip()

    def checks(self):
        return {key:self.sql('BEGIN READ ONLY; SET LOCAL ROLE '+('vision_journal_writer' if key=='runtime_writer' else key)+';'+query+';ROLLBACK;')
                for key,query in self.queries.items()}

    def test_complete_before_after_and_preserved_boundaries(self):
        before=self.sql("SELECT json_build_object('roles',(SELECT json_agg(row_to_json(r) ORDER BY rolname) FROM pg_roles r WHERE rolname LIKE 'vision_journal_%'),"
            "'relations',(SELECT json_agg(json_build_array(c.oid,c.relowner,c.relacl) ORDER BY c.oid) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='vision_effacements'),"
            "'functions',(SELECT json_agg(json_build_array(p.oid,p.proowner,p.proacl) ORDER BY p.oid) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='vision_effacements'))")
        for role in ROLES:
            with self.subTest(before_role=role):
                try:self.sql('BEGIN READ ONLY; SET LOCAL ROLE '+role+';'+self.queries[role]+';ROLLBACK;')
                except subprocess.CalledProcessError as error:self.assertIn(b'permission denied for schema public',error.stderr)
                else:self.fail('historical bootstrap unexpectedly accepted worker query')
        self.assertEqual(self.sql('SET ROLE vision_journal_writer;'+self.queries['runtime_writer']),'f')
        self.assertEqual(self.file(BASE/'journal-public-schema-usage.sql','vision_journal').returncode,0)
        self.assertEqual(self.checks(),{key:'t' for key in self.queries})
        after=self.sql("SELECT json_build_object('roles',(SELECT json_agg(row_to_json(r) ORDER BY rolname) FROM pg_roles r WHERE rolname LIKE 'vision_journal_%'),"
            "'relations',(SELECT json_agg(json_build_array(c.oid,c.relowner,c.relacl) ORDER BY c.oid) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='vision_effacements'),"
            "'functions',(SELECT json_agg(json_build_array(p.oid,p.proowner,p.proacl) ORDER BY p.oid) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='vision_effacements'))")
        self.assertEqual(before,after)
        for role in ROLES:
            self.assertEqual(self.sql("SELECT has_schema_privilege('"+role+"','public','USAGE') AND NOT has_schema_privilege('"+role+"','public','CREATE')"),'t')
        self.assertEqual(self.sql("SELECT NOT has_schema_privilege('vision_journal_import','public','USAGE')"),'t')
        acl=self.sql("SELECT json_agg(json_build_array(r.rolname,a.privilege_type,a.is_grantable) ORDER BY r.rolname,a.privilege_type) FROM pg_namespace n CROSS JOIN LATERAL aclexplode(n.nspacl) a JOIN pg_roles r ON r.oid=a.grantee WHERE n.nspname='public' AND r.rolname LIKE 'vision_journal_%'")
        self.assertEqual(json.loads(acl),[[role,'USAGE',False] for role in sorted(ROLES)])
        self.assertEqual(self.file(BASE/'journal-public-schema-usage.sql','vision_journal').returncode,0)
        self.assertEqual(self.checks(),{key:'t' for key in self.queries})

    def test_wrong_database_closed(self):
        result=self.file(BASE/'journal-public-schema-usage.sql','vision')
        self.assertNotEqual(result.returncode,0)
        self.assertIn(b'journal_namespace_database_refused',result.stderr)

    def test_historical_bootstrap_unchanged(self):
        lock=json.loads((BASE/'journal-bootstrap/source.json').read_text())
        for name,expected in lock['files'].items():
            self.assertEqual(hashlib.sha256((BASE/'journal-bootstrap'/name).read_bytes()).hexdigest(),expected)
        module=(BASE/'database-adoption.nix').read_text()
        old='${psql} --dbname=vision_journal --file=${journal}/bootstrap-journal/03-schema.psql'
        new='${psql} --dbname=vision_journal --file=${./journal-public-schema-usage.sql}'
        self.assertEqual(module.count(new),1)
        self.assertIn(old+'\n    '+new,module)

if __name__=='__main__':unittest.main()
