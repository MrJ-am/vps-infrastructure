import importlib.util
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

BASE=Path(__file__).resolve().parent
ROOT=BASE.parent.parent
spec=importlib.util.spec_from_file_location('contracts_v2',BASE/'preflight_rust_contracts_004_v2.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
PG=Path('/nix/store/hfk2znm53zp4x7hjjh35didm9znjw8jn-postgresql-17.11/bin')
SOURCES=ROOT/'.local/mrjam-plateforme-identity'

class ContractContext(unittest.TestCase):
    def test_global_deadline_stops_remaining_queries_and_closes_output(self):
        output=io.StringIO()
        with contextlib.ExitStack() as stack:
            for obj,name,value in ((p.sys,'argv',['fixed-probe']),
                    (p.os,'geteuid',lambda:0),(p.os,'uname',lambda:SimpleNamespace(nodename='srv1982677')),
                    (p.os.path,'realpath',lambda _:p.PREVIOUS),
                    (p.resource,'setrlimit',lambda *_:None),(p.signal,'signal',lambda *_:None),
                    (p.signal,'alarm',lambda *_:None)):
                stack.enter_context(patch.object(obj,name,value))
            call=stack.enter_context(patch.object(p.subprocess,'run',side_effect=p.ProbeDeadline('SYNTHETIC_PRIVATE_MARKER')))
            with contextlib.redirect_stdout(output):
                self.assertEqual(p.main(),1)
            self.assertEqual(call.call_count,1)
        self.assertEqual(json.loads(output.getvalue()),{'schema_version':2,'code':'RUST_CODE_VERSION_CLASSIFICATION_REFUSED'})

    def test_closed_output_and_query_selectors(self):
        self.assertEqual(p.parse(b't\n'),{'observed':True,'accepted':True})
        self.assertEqual(p.parse(b'f\n'),{'observed':True,'accepted':False})
        for raw in (b'SYNTHETIC_PRIVATE_VALUE',b't\nf\n',b'1\n',b'null\n',b''):
            with self.assertRaises(ValueError):p.parse(raw)
        for context,query in (('public','SELECT true'),('pg_catalog','SELECT true'),('pg_catalog;COMMIT','SELECT true')):
            with self.assertRaises(ValueError):p.sql_for(context,query)
        for context,query in p.QUERIES.values():
            self.assertTrue(p.sql_for(context,query).startswith('BEGIN READ ONLY;'))
            for name in ('vision_creation_contrat','vision_revision_contrat'):
                self.assertNotIn('public.'+name+'()',query.replace("'public."+name+"()'",''))

    def test_exact_witness_construction_preserved(self):
        for file,lecture in (('016_creation_semantique.sql',p.CREATION),('017_tutorat_temps.sql',p.REVISION)):
            self.assertIn('lecture:=$sql$'+lecture+'$sql$;',
                (SOURCES/'components/vision/migrations'/file).read_text())

    def test_native_postgresql_context_and_separate_permission_classification(self):
        self.assertNotEqual(os.geteuid(),0)
        with tempfile.TemporaryDirectory(prefix='mrjam-closed-witness-context-') as temporary:
            root=Path(temporary);data=root/'pg'
            def run(args):
                return subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
            self.assertEqual(run([str(PG/'initdb'),'-D',str(data),'--no-locale','--auth=trust']).returncode,0)
            self.assertEqual(run([str(PG/'pg_ctl'),'-D',str(data),'-l',str(root/'log'),'-o',
                '-c listen_addresses= -c unix_socket_directories='+temporary,'-w','start']).returncode,0)
            try:
                def sql(text):
                    result=run([str(PG/'psql'),'-X','-w','-qAt','-h',temporary,'-d','postgres',
                        '-v','ON_ERROR_STOP=1','-c',text])
                    self.assertEqual(result.returncode,0,'native SQL result');return result.stdout
                def observed():
                    return {key:p.parse(sql(p.sql_for(context,query)))['accepted']
                            for key,(context,query) in p.QUERIES.items()}
                sql('CREATE ROLE vision LOGIN;CREATE ROLE audition_app LOGIN;'
                    'CREATE TABLE public.vision_schema_migrations(version bigint);'
                    'INSERT INTO public.vision_schema_migrations SELECT generate_series(1,27);'
                    'GRANT SELECT ON public.vision_schema_migrations TO vision;'
                    'CREATE TYPE public.synthetic_vector AS (n integer);')
                sql((SOURCES/'crates/audition/migrations/001-schema.sql').read_text())
                sql('GRANT USAGE ON SCHEMA audition TO audition_app;'
                    'GRANT SELECT ON audition.schema_migrations TO audition_app;')
                for name in ('vision_ecrire_item','vision_evaluer'):
                    sql('CREATE FUNCTION public.'+name+'(x public.synthetic_vector) RETURNS public.synthetic_vector '
                        "LANGUAGE sql STABLE AS 'SELECT x';")
                for name,lecture,number in (('vision_creation_contrat',p.CREATION,1),('vision_revision_contrat',p.REVISION,7)):
                    digest=sql('SET search_path=public,pg_catalog;'+lecture).decode().strip()
                    body='SELECT CASE WHEN ('+lecture+')='+p.literal(digest)+' THEN '+str(number)+' ELSE 0 END'
                    sql('CREATE FUNCTION public.'+name+'() RETURNS integer LANGUAGE sql STABLE AS '+p.literal(body))
                    self.assertEqual(sql('SET search_path=public,pg_catalog;SELECT public.'+name+'();'),str(number).encode()+b'\n')
                with self.subTest('runtime context accepts genuine witnesses; catalog-only context falsely refuses'):
                    state=observed()
                    for prefix in ('vision_creation','vision_revision'):
                        self.assertTrue(state[prefix+'_witness_expected_shape'])
                        self.assertTrue(state[prefix+'_witness_execute_granted'])
                        self.assertTrue(state[prefix+'_witness_matches_runtime_context'])
                        self.assertFalse(state[prefix+'_witness_matches_catalog_context'])
                    self.assertTrue(state['audition_versions_exactly_1'])
                    self.assertTrue(state['audition_version_select_granted'])
                    self.assertFalse(state['audition_maximum_version_is_2'])
                with self.subTest('exact Audition migration distinguishes version2 from revoked SELECT'):
                    sql((SOURCES/'crates/audition/migrations/002-version-scope.sql').read_text())
                    state=observed()
                    self.assertTrue(state['audition_versions_exactly_1_and_2'])
                    self.assertTrue(state['audition_maximum_version_is_2'])
                    sql('REVOKE SELECT ON audition.schema_migrations FROM audition_app;')
                    state=observed()
                    self.assertTrue(state['audition_maximum_version_is_2'])
                    self.assertFalse(state['audition_version_select_granted'])
                with self.subTest('real drift stays refused under both contexts'):
                    sql("CREATE OR REPLACE FUNCTION public.vision_ecrire_item(x public.synthetic_vector) RETURNS public.synthetic_vector LANGUAGE sql STABLE AS 'SELECT $1';")
                    state=observed()
                    self.assertFalse(state['vision_creation_witness_matches_runtime_context'])
                    self.assertFalse(state['vision_creation_witness_matches_catalog_context'])
                    self.assertTrue(state['vision_revision_witness_matches_runtime_context'])
                with self.subTest('execution privilege and function-local search_path remain independent'):
                    sql('REVOKE EXECUTE ON FUNCTION public.vision_revision_contrat() FROM PUBLIC,vision;')
                    state=observed()
                    self.assertFalse(state['vision_revision_witness_execute_granted'])
                    self.assertTrue(state['vision_revision_witness_matches_runtime_context'])
                    sql('ALTER FUNCTION public.vision_revision_contrat() SET search_path=pg_catalog;')
                    self.assertFalse(observed()['vision_revision_witness_expected_shape'])
                with self.subTest('unknown version remains unclassified'):
                    sql('INSERT INTO audition.schema_migrations VALUES(3);')
                    state=observed()
                    for name in ('audition_versions_exactly_1','audition_versions_exactly_1_and_2','audition_maximum_version_is_2'):
                        self.assertFalse(state[name])
                with self.subTest('public homonyms are never executed or queried and are explicitly classified'):
                    self.assertTrue(observed()['vision_witness_runtime_names_unshadowed'])
                    sql("CREATE FUNCTION public.pg_get_functiondef(oid) RETURNS text LANGUAGE plpgsql AS $$BEGIN RAISE EXCEPTION 'SYNTHETIC_FORBIDDEN_CALL';END$$;"
                        "CREATE VIEW public.pg_proc AS SELECT * FROM pg_catalog.pg_proc WHERE false;")
                    state=observed()
                    self.assertFalse(state['vision_witness_runtime_names_unshadowed'])
                    self.assertTrue(state['vision_revision_witness_matches_runtime_context'])
                    for kind in ('oid','text','name'):
                        sql('CREATE FUNCTION public.synthetic_equal_'+kind+'('+kind+','+kind+") RETURNS boolean LANGUAGE plpgsql AS $$BEGIN RAISE EXCEPTION 'SYNTHETIC_FORBIDDEN_OPERATOR';END$$;"
                            'CREATE OPERATOR public.= (LEFTARG='+kind+',RIGHTARG='+kind+',FUNCTION=public.synthetic_equal_'+kind+');')
                    state=observed()
                    self.assertFalse(state['vision_witness_runtime_names_unshadowed'])
                    self.assertTrue(state['vision_revision_witness_matches_runtime_context'])
            finally:
                self.assertEqual(run([str(PG/'pg_ctl'),'-D',str(data),'-m','immediate','-w','stop']).returncode,0)

if __name__=='__main__':unittest.main()
