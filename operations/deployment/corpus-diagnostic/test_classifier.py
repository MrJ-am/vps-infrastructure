import copy
import hashlib
import json
from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[3]
BINARY=Path('/nix/store/anvdal9pag7qh6w13cn88mw1pdlyiky2-mrjam-mateval-corpus-classifier-1/bin/mrjam-mateval-corpus-classifier')
BANK=Path('/nix/store/pdaay31fv76dxgmp1ar4xwhnbhb6fwyp-mrjam-reviewed-mrjam-qualified-artifacts-8bf05fb9065a-mateval/data/bank.json')

class ActualRustTypes(unittest.TestCase):
    def observe(self,value):
        run=subprocess.run([str(BINARY)],input=json.dumps(value).encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5)
        self.assertEqual(run.returncode,0);self.assertEqual(run.stderr,b'')
        result=json.loads(run.stdout);self.assertEqual(result['code'],'MATHEVAL_TYPED_CORPUS_CLASSIFIED')
        self.assertTrue(all(type(v) is bool for v in result['checks'].values()))
        self.assertLess(len(run.stdout),2048)
        return result['checks']

    def test_source_types_byte_identical_and_public_bank_exact(self):
        source=Path(__file__).with_name('src')/'types.rs'
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),'aed36e3ab6058d6756f3e8a6198b5a5df4c4af32e5d1eeef3f95eeed4312674c')
        lock=json.loads((ROOT/'operations/builds/sources-runtime-20261031.lock.json').read_bytes())
        self.assertEqual(lock['sources']['mateval']['files']['src/types.rs'],hashlib.sha256(source.read_bytes()).hexdigest())
        value=self.observe(json.loads(BANK.read_bytes()))
        self.assertTrue(all(v for k,v in value.items() if not k.startswith('extra_')))
        self.assertFalse(any(v for k,v in value.items() if k.startswith('extra_')))

    def test_unknown_fields_are_the_only_lossy_type_projection(self):
        for level in ('root','question','production'):
            bank=json.loads(BANK.read_bytes())
            target={'root':bank,'question':bank['questions'][0],'production':bank['questions'][0]['productions'][0]}[level]
            target['invented-extra-private-marker']='invented-private-value'
            value=self.observe(bank)
            self.assertFalse(value['raw_json_equal']);self.assertTrue(value['typed_json_equal'])
            self.assertTrue(value['extra_'+level+'_fields_present'])
            self.assertNotIn('invented-private-value',json.dumps(value))

    def test_scientific_text_and_array_order_differences_remain_visible(self):
        for field,expected in (('statement','question_statements_equal'),('content','production_contents_equal')):
            bank=json.loads(BANK.read_bytes())
            target=bank['questions'][0] if field=='statement' else bank['questions'][0]['productions'][0]
            target[field]+=' invented difference'
            value=self.observe(bank)
            self.assertFalse(value['typed_json_equal']);self.assertFalse(value[expected]);self.assertTrue(value['typed_validation_accepted'])
        bank=json.loads(BANK.read_bytes());bank['questions'].reverse()
        value=self.observe(bank);self.assertFalse(value['question_ids_and_order_equal']);self.assertFalse(value['typed_json_equal'])

    def test_missing_fields_have_no_default_and_invalid_ids_refused(self):
        bank=json.loads(BANK.read_bytes());del bank['questions'][0]['statement']
        value=self.observe(bank);self.assertFalse(value['typed_deserialization_accepted']);self.assertFalse(value['typed_json_equal'])
        bank=json.loads(BANK.read_bytes());bank['questions'][0]['id']='bad'
        value=self.observe(bank);self.assertTrue(value['typed_deserialization_accepted']);self.assertFalse(value['typed_validation_accepted'])

    def test_invalid_bounded_input_returns_only_closed_refusal(self):
        for payload,args in ((b'private-not-json',[]),(b' '*((5*1024**2)+1),[]),(b'{}',['private-argument'])):
            run=subprocess.run([str(BINARY)]+args,input=payload,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5)
            self.assertEqual(run.returncode,1);self.assertEqual(run.stderr,b'')
            self.assertEqual(json.loads(run.stdout),{'schema_version':1,'code':'MATHEVAL_TYPED_CORPUS_REFUSED'})

if __name__=='__main__':unittest.main()
