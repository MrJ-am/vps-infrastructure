import json
import unittest
import preflight_generation as m


class GenerationMetadata(unittest.TestCase):
    def test_current_nix_shape_exports_only_three_public_fields(self):
        item={'narHash':'sha256-'+'A'*43+'=','narSize':1234,'references':['not-exported'],'deriver':'not-exported'}
        result=m.parse(json.dumps({m.PREVIOUS:item}).encode())
        self.assertEqual(set(result),{'generation','nar_hash','nar_bytes'})
        self.assertNotIn('not-exported',str(result))

    def test_older_nix_array_is_supported_without_other_paths(self):
        item={'path':m.PREVIOUS,'narHash':'sha256-'+'A'*43+'=','narSize':1234}
        self.assertEqual(m.parse(json.dumps([item]).encode())['nar_bytes'],1234)
        with self.assertRaises(ValueError):m.parse(json.dumps([item,item]).encode())
        item['path']='/other'
        with self.assertRaises(ValueError):m.parse(json.dumps([item]).encode())

    def test_invalid_or_oversized_values_refused(self):
        for raw in (b'x'*65537,b'[]',b'null',b'{}',b'{"secret":"not-exported"}'):
            with self.assertRaises(ValueError):m.parse(raw)


if __name__=='__main__':
    unittest.main()
