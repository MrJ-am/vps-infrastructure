import json
import unittest
from preflight_previous_closure import parse, PREVIOUS, PREVIOUS_NAR


class ClosureMetadataTest(unittest.TestCase):
    def item(self):
        return {'path':PREVIOUS,'narHash':PREVIOUS_NAR,'narSize':200488,
                'unrelated':'THIS_FIELD_MUST_NEVER_ESCAPE'}

    def test_only_fixed_metadata_escapes_for_both_nix_formats(self):
        item=self.item()
        for value in ([item],{PREVIOUS:{k:v for k,v in item.items() if k!='path'}}):
            output=parse(json.dumps(value).encode())
            self.assertEqual(output,{'generation':PREVIOUS,'artifacts':{PREVIOUS:PREVIOUS_NAR},'nar_bytes':200488})

    def test_malformed_duplicate_or_wrong_generation_never_return_partial(self):
        item=self.item()
        for value in ([item,item],[dict(item,path='/var/lib/private')],
                      [dict(item,narHash='sha256-'+'A'*43+'=')],[dict(item,narSize=True)],[]):
            with self.subTest(value=value),self.assertRaises(ValueError):parse(json.dumps(value).encode())
        with self.assertRaises(ValueError):parse(b'{"duplicate":1,"duplicate":2}')


if __name__=='__main__':unittest.main()
