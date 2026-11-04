import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

BASE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('builder',BASE/'build_sql.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
PG=Path('/nix/store/0xml3ipsrjdp9sms6igsw46bzwaqwbr8-postgresql-and-plugins-17.11/bin')

class GuardedAudition(unittest.TestCase):
    def test_exact_sources_and_builder_are_deterministic(self):
        a=p.documents();self.assertEqual(a,p.documents())
        body=(BASE/'002-additive.sql').read_text()
        body='\n'.join(line for line in body.splitlines() if line not in ('BEGIN;','COMMIT;'))
        self.assertIn(body,a[1])
        self.assertTrue(a[0].startswith('BEGIN READ ONLY;'))
        self.assertNotIn('UPDATE ',a[1])
        self.assertNotIn('DELETE ',a[1])

    def test_real_postgresql_preserves_rows_and_refuses_unrecognized_catalogues(self):
        self.assertNotEqual(os.geteuid(),0)
        preflight,adopt=p.documents()
        with tempfile.TemporaryDirectory(prefix='mrjam-audition-v2-') as tmp:
            root=Path(tmp);data=root/'pg'
            def run(args):return subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
            self.assertEqual(run([str(PG/'initdb'),'-U','postgres','-D',str(data),'--no-locale','--encoding=UTF8','--auth=trust']).returncode,0)
            self.assertEqual(run([str(PG/'pg_ctl'),'-D',str(data),'-l',str(root/'log'),'-o',
                '-c listen_addresses= -c unix_socket_directories='+tmp,'-w','start']).returncode,0)
            try:
                def sql(text,db='vision',success=True):
                    result=run([str(PG/'psql'),'-U','postgres','-X','-w','-qAt','-h',tmp,'-d',db,'-v','ON_ERROR_STOP=1','-c',text])
                    self.assertEqual(result.returncode==0,success,'native SQL result');return result.stdout
                sql('CREATE ROLE audition_app LOGIN;',db='postgres')
                sql('CREATE DATABASE vision;',db='postgres')
                def seed():
                    sql('DROP SCHEMA IF EXISTS audition CASCADE;')
                    sql((BASE/'001-reference.sql').read_text())
                    sql("GRANT USAGE ON SCHEMA audition TO audition_app;GRANT SELECT ON audition.schema_migrations TO audition_app;"
                        "INSERT INTO audition.administrateurs VALUES('invented.admin',true);"
                        "INSERT INTO audition.groupes VALUES('invented-group','Invented group');"
                        "INSERT INTO audition.objets VALUES('invented-object','invented-group','cours',1,'{}','2026-01-01');"
                        "INSERT INTO audition.versions VALUES('invented-object','invented-group',1,'{}','invented.admin','2026-01-01');")
                def dump():
                    result=run([str(PG/'pg_dump'),'-U','postgres','-h',tmp,'-d','vision','--data-only','--no-owner','--no-privileges','--exclude-table=audition.schema_migrations'])
                    self.assertEqual(result.returncode,0)
                    return b'\n'.join(line for line in result.stdout.splitlines() if not line.startswith((b'\\restrict ',b'\\unrestrict ')))
                def projection():return json.loads(sql(preflight))
                with self.subTest('exact 001 is applicable and rows survive 002'):
                    seed();state=projection()
                    self.assertTrue(state['known_schema_001']);self.assertFalse(state['known_schema_002'])
                    self.assertTrue(all(v for k,v in state.items() if k not in ('known_schema_002','versions_exactly_1_and_2')))
                    self.assertEqual(sql("SELECT bool_and(polroles=ARRAY[0]::oid[]) FROM pg_policy WHERE polrelid IN(SELECT oid FROM pg_class WHERE relnamespace='audition'::regnamespace)"),b't\n')
                    before=dump();sql(adopt);self.assertEqual(before,dump())
                    state=projection();self.assertTrue(state['known_schema_002']);self.assertTrue(state['versions_exactly_1_and_2'])
                with self.subTest('exact already-adopted state leaves policy objects and rows unchanged'):
                    policies=sql("SELECT array_agg(oid ORDER BY oid) FROM pg_policy WHERE polrelid IN(SELECT oid FROM pg_class WHERE relnamespace='audition'::regnamespace)")
                    sql(adopt);self.assertEqual(before,dump())
                    self.assertEqual(policies,sql("SELECT array_agg(oid ORDER BY oid) FROM pg_policy WHERE polrelid IN(SELECT oid FROM pg_class WHERE relnamespace='audition'::regnamespace)"))
                for title,change in (
                    ('policy drift',"ALTER POLICY versions_lecture ON audition.versions USING(true)"),
                    ('column drift',"ALTER TABLE audition.objets ADD COLUMN unexpected integer"),
                    ('function drift',"CREATE OR REPLACE FUNCTION audition.est_admin() RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS 'SELECT true'"),
                    ('RLS drift',"ALTER TABLE audition.versions DISABLE ROW LEVEL SECURITY"),
                    ('extra object',"CREATE TABLE audition.unexpected(x integer)"),
                    ('unknown version',"INSERT INTO audition.schema_migrations VALUES(3)"),
                    ('application owns schema',"ALTER SCHEMA audition OWNER TO audition_app"),
                    ('unexpected role privilege',"ALTER ROLE audition_app CREATEDB"),
                ):
                    with self.subTest(title):
                        seed();sql(change);before=dump();sql(adopt,success=False);self.assertEqual(before,dump())
                        self.assertEqual(sql('SELECT array_agg(version ORDER BY version) FROM audition.schema_migrations'),b'{1,3}\n' if title=='unknown version' else b'{1}\n')
                        sql('ALTER ROLE audition_app NOCREATEDB;')
            finally:
                self.assertEqual(run([str(PG/'pg_ctl'),'-D',str(data),'-m','immediate','-w','stop']).returncode,0)

if __name__=='__main__':unittest.main()
