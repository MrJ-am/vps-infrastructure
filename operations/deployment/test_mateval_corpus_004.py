import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

BASE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('corpus',BASE/'preflight_mateval_corpus_004.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
PG=Path('/nix/store/hfk2znm53zp4x7hjjh35didm9znjw8jn-postgresql-17.11/bin')

class CorpusProjection(unittest.TestCase):
    def test_bound_public_input_and_closed_result(self):
        self.assertIsInstance(p.public_bank()['version'],str)
        good={key:False for key in p.FIELDS}
        self.assertEqual(p.parse(json.dumps(good)),good)
        for bad in ({**good,'version':'private'},{**good,'selected_bank_equal':1}):
            with self.assertRaises(ValueError):p.parse(json.dumps(bad))

    def test_native_absence_collision_equality_and_no_values_exported(self):
        self.assertNotEqual(os.geteuid(),0)
        with tempfile.TemporaryDirectory(prefix='mrjam-corpus-projection-') as tmp:
            root=Path(tmp);data=root/'data'
            def run(args):return subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
            self.assertEqual(run([str(PG/'initdb'),'-D',str(data),'--no-locale','--auth=trust']).returncode,0)
            self.assertEqual(run([str(PG/'pg_ctl'),'-D',str(data),'-l',str(root/'log'),'-o',
                '-c listen_addresses= -c unix_socket_directories='+tmp,'-w','start']).returncode,0)
            try:
                def sql(text):
                    result=run([str(PG/'psql'),'-X','-w','-qAt','-h',tmp,'-d','postgres','-v','ON_ERROR_STOP=1','-c',text])
                    self.assertEqual(result.returncode,0,'native SQL outcome');return result.stdout
                sql('CREATE TABLE corpus(version text PRIMARY KEY,bank jsonb,codebook jsonb,digest text);')
                bank={'version':"synthetic'v1",'unknown_field_retained':'public-value'}
                baseline=sql(p.query(bank));self.assertFalse(any(p.parse(baseline).values()))
                old={'version':bank['version'],'different':'synthetic-old'}
                sql('INSERT INTO corpus VALUES('+p.literal(bank['version'])+','+p.literal(json.dumps(old))+",'{\"private-invented-reference\":1}',"+p.literal('a'*64)+');')
                value=p.parse(sql(p.query(bank)))
                self.assertTrue(value['selected_version_present']);self.assertTrue(value['selected_version_unique'])
                self.assertFalse(value['selected_bank_equal']);self.assertTrue(value['selected_bank_version_matches_key'])
                self.assertTrue(value['selected_codebook_nonempty']);self.assertTrue(value['selected_digest_is_lowercase_sha256'])
                self.assertNotIn('private-invented-reference',json.dumps(value))
                # Fixture mutation only: prove the predicate changes with exact JSON equality.
                sql('UPDATE corpus SET bank='+p.literal(json.dumps(bank))+';')
                self.assertTrue(p.parse(sql(p.query(bank)))['selected_bank_equal'])
                sql("UPDATE corpus SET digest='not-sha',codebook='null';")
                value=p.parse(sql(p.query(bank)))
                self.assertFalse(value['selected_digest_is_lowercase_sha256']);self.assertFalse(value['selected_codebook_is_object'])
                self.assertEqual(sql('SELECT count(*) FROM corpus;'),b'1\n')
            finally:self.assertEqual(run([str(PG/'pg_ctl'),'-D',str(data),'-m','immediate','-w','stop']).returncode,0)

if __name__=='__main__':unittest.main()
