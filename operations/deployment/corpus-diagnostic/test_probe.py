import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

BASE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('probe',BASE/'probe.py');p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
PG=Path('/nix/store/hfk2znm53zp4x7hjjh35didm9znjw8jn-postgresql-17.11/bin')
BANK=Path('/nix/store/pdaay31fv76dxgmp1ar4xwhnbhb6fwyp-mrjam-reviewed-mrjam-qualified-artifacts-8bf05fb9065a-mateval/data/bank.json')

class ClosedPipeline(unittest.TestCase):
    def test_parser_never_returns_arbitrary_fields(self):
        p.classifier_verified()
        value={'schema_version':1,'code':'MATHEVAL_TYPED_CORPUS_CLASSIFIED','checks':{k:True for k in p.FIELDS},
            'corpus_values_exported':False,'codebook_read':False,'mutation_performed':False}
        self.assertEqual(p.result(json.dumps(value)),value)
        for bad in ({**value,'private':'invented'}, {**value,'schema_version':True},
            {**value,'checks':{**value['checks'],'raw_json_equal':'invented'}}, {**value,'codebook_read':True}):
            with self.assertRaises(ValueError):p.result(json.dumps(bad))

    def test_real_pg_to_exact_rust_types_local_pipe_only(self):
        self.assertNotEqual(os.geteuid(),0)
        with tempfile.TemporaryDirectory(prefix='mrjam-typed-corpus-') as tmp:
            root=Path(tmp);data=root/'pg'
            def run(args,**kw):return subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30,**kw)
            self.assertEqual(run([str(PG/'initdb'),'-D',str(data),'--no-locale','--encoding=UTF8','--auth=trust']).returncode,0)
            self.assertEqual(run([str(PG/'pg_ctl'),'-D',str(data),'-l',str(root/'log'),'-o',
                '-c listen_addresses= -c unix_socket_directories='+tmp,'-w','start']).returncode,0)
            try:
                def sql(text):
                    result=run([str(PG/'psql'),'-X','-w','-qAt','-h',tmp,'-d','postgres','-v','ON_ERROR_STOP=1'],input=text.encode())
                    self.assertEqual(result.returncode,0,'native SQL outcome');return result.stdout
                bank=json.loads(BANK.read_bytes());bank['invented-extra-field']='invented-private-marker'
                literal=lambda v:"'"+v.replace("'","''")+"'"
                sql('CREATE ROLE matheval_app LOGIN;CREATE TABLE corpus(version text,bank jsonb,codebook jsonb);'
                    'GRANT SELECT(version,bank) ON corpus TO matheval_app;INSERT INTO corpus VALUES(\'0.3.0\','+
                    literal(json.dumps(bank))+",'{\"not-readable-codebook-marker\":true}');")
                raw=sql(p.SQL)
                self.assertNotIn(b'not-readable-codebook-marker',raw)
                value=run([p.BINARY],input=raw)
                self.assertEqual(value.returncode,0);result=p.result(value.stdout)
                self.assertTrue(result['checks']['typed_json_equal']);self.assertFalse(result['checks']['raw_json_equal'])
                self.assertNotIn('invented-private-marker',json.dumps(result))
                self.assertEqual(sql('SELECT count(*) FROM corpus;'),b'1\n')
                # Native SQL refuses writes under the exact transaction setting.
                failed=run([str(PG/'psql'),'-X','-w','-qAt','-h',tmp,'-d','postgres','-v','ON_ERROR_STOP=1'],
                    input=b'BEGIN READ ONLY;DELETE FROM corpus;ROLLBACK;')
                self.assertNotEqual(failed.returncode,0)
                self.assertEqual(sql('SELECT count(*) FROM corpus;'),b'1\n')
            finally:self.assertEqual(run([str(PG/'pg_ctl'),'-D',str(data),'-m','immediate','-w','stop']).returncode,0)

if __name__=='__main__':unittest.main()
