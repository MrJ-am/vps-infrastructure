import ast
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

BASE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('names',BASE/'preflight_rust_catalog_names_004.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
PG=Path('/nix/store/0xml3ipsrjdp9sms6igsw46bzwaqwbr8-postgresql-and-plugins-17.11/bin')

class CatalogueNames(unittest.TestCase):
    def test_only_fixed_boolean_catalogue_queries(self):
        self.assertEqual(len(p.QUERIES),8)
        for context,query in p.QUERIES.values():
            self.assertEqual(context,'pg_catalog')
            self.assertTrue(p.sql_for(context,query).startswith('BEGIN READ ONLY;'))
        for raw in (b'PRIVATE_SYNTHETIC_MARKER',b'1',b't\nf\n',b'null\n'):
            with self.assertRaises(ValueError):p.parse(raw)
        self.assertEqual(p.parse(b't\n'),{'observed':True,'accepted':True})

    def test_execution_engine_unchanged_except_fixed_schema_and_output_labels(self):
        old=(BASE/'preflight_rust_contracts_004_v2.py').read_text()
        new=(BASE/'preflight_rust_catalog_names_004.py').read_text()
        new=new.replace("'schema_version':3","'schema_version':2").replace('"schema_version":3','"schema_version":2')
        new=new.replace('RUST_CATALOG_NAMES_CLASSIFIED','RUST_CODE_VERSION_GUARDS_CLASSIFIED')
        new=new.replace('RUST_CATALOG_NAMES_CLASSIFICATION_REFUSED','RUST_CODE_VERSION_CLASSIFICATION_REFUSED')
        new=new.replace("'migration_version_metadata_read':False","'migration_version_metadata_read':True")
        for name in ('parse','sql_for','main'):
            pick=lambda text:next(n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name==name)
            self.assertEqual(ast.dump(pick(old)),ast.dump(pick(new)))

    def test_native_pgvector_and_relevant_homonyms(self):
        self.assertNotEqual(os.geteuid(),0)
        with tempfile.TemporaryDirectory(prefix='mrjam-vector-catalogue-') as tmp:
            root=Path(tmp);data=root/'pg'
            def run(args):return subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
            self.assertEqual(run([str(PG/'initdb'),'-D',str(data),'--no-locale','--auth=trust']).returncode,0)
            self.assertEqual(run([str(PG/'pg_ctl'),'-p',str(PG/'postgres'),'-D',str(data),'-l',str(root/'log'),'-o',
                '-c listen_addresses= -c unix_socket_directories='+tmp,'-w','start']).returncode,0)
            try:
                def sql(text):
                    result=run([str(PG/'psql'),'-X','-w','-qAt','-h',tmp,'-d','postgres','-v','ON_ERROR_STOP=1','-c',text])
                    self.assertEqual(result.returncode,0,'native SQL outcome');return result.stdout
                def observed():return {k:p.parse(sql(p.sql_for(*v)))['accepted'] for k,v in p.QUERIES.items()}
                sql('CREATE EXTENSION vector;')
                self.assertTrue(all(observed().values()))
                sql("CREATE FUNCTION public.synthetic_equal(text,text) RETURNS boolean LANGUAGE plpgsql AS $$BEGIN RAISE EXCEPTION 'DO_NOT_CALL';END$$;"
                    'CREATE OPERATOR public.= (LEFTARG=text,RIGHTARG=text,FUNCTION=public.synthetic_equal);')
                state=observed()
                self.assertFalse(state['public_runtime_type_equality_homonyms_absent'])
                self.assertFalse(state['public_equality_operators_all_pgvector_members'])
                self.assertFalse(state['public_equality_operands_all_expected_vector_types'])
                sql("CREATE FUNCTION public.pg_get_functiondef(oid) RETURNS text LANGUAGE plpgsql AS $$BEGIN RAISE EXCEPTION 'DO_NOT_CALL';END$$;"
                    "CREATE VIEW public.pg_proc AS SELECT * FROM pg_catalog.pg_proc WHERE false;")
                state=observed()
                self.assertFalse(state['public_pg_get_functiondef_homonym_absent'])
                self.assertFalse(state['public_pg_proc_relation_absent'])
                self.assertTrue(state['public_md5_homonym_absent'])
                self.assertTrue(state['public_string_agg_homonym_absent'])
            finally:
                self.assertEqual(run([str(PG/'pg_ctl'),'-D',str(data),'-m','immediate','-w','stop']).returncode,0)

if __name__=='__main__':unittest.main()
