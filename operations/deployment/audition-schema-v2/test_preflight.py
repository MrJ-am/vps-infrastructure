import importlib.util
import json
from pathlib import Path
import unittest

BASE=Path(__file__).resolve().parent
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
p=module('preflight',BASE.parent/'preflight_audition_schema_004.py')
b=module('builder',BASE/'build_sql.py')

class ClosedAuditionProbe(unittest.TestCase):
    def test_sql_is_the_exact_qualified_read_only_guard(self):
        self.assertEqual(p.SQL,b.documents()[0])
        self.assertTrue(p.SQL.startswith('BEGIN READ ONLY;'))
        self.assertTrue(p.SQL.endswith('ROLLBACK;\n'))

    def test_output_refuses_unknown_values_keys_duplicates_and_non_booleans(self):
        valid={key:True for key in p.KEYS}
        self.assertEqual(p.parse(json.dumps(valid).encode()),valid)
        invalid=[b'PRIVATE_SYNTHETIC_VALUE',b'[]',b'{}',b'null',b'x'*2049]
        for key in p.KEYS:
            invalid.extend([json.dumps(dict(valid,**{key:1})).encode(),
                            json.dumps(dict(valid,**{key:'PRIVATE_SYNTHETIC_VALUE'})).encode()])
        invalid.append(json.dumps(dict(valid,unexpected=False)).encode())
        invalid.append(json.dumps(valid).replace('{','{"database_is_vision":false,',1).encode())
        for raw in invalid:
            with self.assertRaises((ValueError,TypeError)):p.parse(raw)

if __name__=='__main__':unittest.main()
