import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

BASE=Path(__file__).resolve().parent
ROOT=BASE.parent.parent
spec=importlib.util.spec_from_file_location('contracts',BASE/'preflight_rust_contracts_004.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
PG=Path('/nix/store/hfk2znm53zp4x7hjjh35didm9znjw8jn-postgresql-17.11/bin')
SOURCE=ROOT/'.local/ci-artifact-recovery-20261102/proposal-base/sources/vision/migrations'

class CodeWitnesses(unittest.TestCase):
    def test_exact_migration_code_and_closed_projection(self):
        for file,lecture in (('016_creation_semantique.sql',p.CREATION),('017_tutorat_temps.sql',p.REVISION)):
            text=(SOURCE/file).read_text()
            self.assertIn('lecture:=$sql$'+lecture+'$sql$;',text)
        self.assertEqual(p.parse(b't\n'),{'observed':True,'accepted':True})
        for bad in (b'private',b't\nf\n',b'1\n',b'null\n'):
            with self.assertRaises(ValueError):p.parse(bad)
        for query in p.QUERIES.values():
            self.assertNotIn('public.vision_creation_contrat()',query.replace("'public.vision_creation_contrat()'",''))
            self.assertNotIn('public.vision_revision_contrat()',query.replace("'public.vision_revision_contrat()'",''))

    def test_real_postgresql_witnesses_and_versions_tamper_closed(self):
        self.assertNotEqual(os.geteuid(),0)
        with tempfile.TemporaryDirectory(prefix='mrjam-code-witness-') as temporary:
            root=Path(temporary);data=root/'pg'
            def run(args):return subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
            self.assertEqual(run([str(PG/'initdb'),'-D',str(data),'--no-locale','--auth=trust']).returncode,0)
            self.assertEqual(run([str(PG/'pg_ctl'),'-D',str(data),'-l',str(root/'log'),'-o',
                '-c listen_addresses= -c unix_socket_directories='+temporary,'-w','start']).returncode,0)
            try:
                def sql(text):
                    result=run([str(PG/'psql'),'-X','-w','-qAt','-h',temporary,'-d','postgres','-v','ON_ERROR_STOP=1','-c',text])
                    self.assertEqual(result.returncode,0,'native SQL outcome');return result.stdout
                sql('CREATE ROLE vision LOGIN;CREATE ROLE audition_app LOGIN;CREATE SCHEMA audition;'
                    'CREATE TABLE public.vision_schema_migrations(version bigint);INSERT INTO public.vision_schema_migrations SELECT generate_series(1,27);'
                    'CREATE TABLE audition.schema_migrations(version integer);INSERT INTO audition.schema_migrations VALUES(1),(2);'
                    'GRANT SELECT ON public.vision_schema_migrations TO vision;GRANT SELECT ON audition.schema_migrations TO audition_app;')
                for name in ('vision_ecrire_item','vision_evaluer'):
                    sql('CREATE FUNCTION public.'+name+"() RETURNS integer LANGUAGE sql STABLE AS 'SELECT 1';")
                for name,lecture,number in (('vision_creation_contrat',p.CREATION,1),('vision_revision_contrat',p.REVISION,7)):
                    digest=sql(lecture).decode().strip()
                    body='SELECT CASE WHEN ('+lecture+')='+p.literal(digest)+' THEN '+str(number)+' ELSE 0 END'
                    sql('CREATE FUNCTION public.'+name+'() RETURNS integer LANGUAGE sql STABLE AS '+p.literal(body)+';')
                    self.assertEqual(sql('SELECT public.'+name+'();'),str(number).encode()+b'\n')
                def observed():
                    return {k:p.parse(sql("BEGIN READ ONLY;SET LOCAL search_path=pg_catalog;"+v+';ROLLBACK;'))['accepted'] for k,v in p.QUERIES.items()}
                self.assertTrue(all(observed().values()))
                sql("CREATE OR REPLACE FUNCTION public.vision_ecrire_item() RETURNS integer LANGUAGE sql STABLE AS 'SELECT 2';")
                state=observed();self.assertFalse(state['vision_creation_witness_matches_current_catalog'])
                self.assertTrue(state['vision_revision_witness_matches_current_catalog'])
                self.assertEqual(sql('SELECT public.vision_creation_contrat();'),b'0\n')
                sql('DELETE FROM public.vision_schema_migrations WHERE version=27;UPDATE audition.schema_migrations SET version=3 WHERE version=2;')
                state=observed();self.assertFalse(state['vision_schema_versions_1_through_27']);self.assertFalse(state['audition_schema_version_2'])
                sql("CREATE OR REPLACE FUNCTION public.vision_revision_contrat() RETURNS integer LANGUAGE sql STABLE AS 'SELECT 7';")
                self.assertFalse(observed()['vision_revision_witness_matches_current_catalog'])
            finally:self.assertEqual(run([str(PG/'pg_ctl'),'-D',str(data),'-m','immediate','-w','stop']).returncode,0)

if __name__=='__main__':unittest.main()
