"""A child receipt cannot replace the immutable source binding."""
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
import consumer_identity as C


class Rebinding(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.bundle=Path(self.temp.name)/'identity'
        shutil.copytree(os.environ['SIGNATURE_IDENTITY'],self.bundle)
        self.source=Path(os.environ['SIGNATURE_CAPTURE'])
        self.revision='17194087eec9162bb5372221c43e1de0501dfe6a'

    def load(self):
        return C.load(self.bundle,self.source,self.revision)

    def manifest(self,change):
        path=self.bundle/'manifest.json';value=json.loads(path.read_bytes())
        change(value);path.write_text(json.dumps(value))

    def test_valid_job_loads_seven_resources(self):
        self.assertEqual(len(self.load()),7)

    def test_self_consistent_forged_resource_is_refused(self):
        raw=b'/* forged CSS */';(self.bundle/'signature.css').write_bytes(raw)
        self.manifest(lambda m:m['resources'].__setitem__('signature.css',{'sha256':C.sha(raw),'bytes':len(raw)}))
        with self.assertRaisesRegex(ValueError,'SIGNATURE_BUNDLE_INPUT_CHANGED'):
            self.load()

    def test_wrong_input_binding_is_refused(self):
        self.manifest(lambda m:m['input_sha256'].__setitem__('mrjam.sty','0'*64))
        with self.assertRaisesRegex(ValueError,'SIGNATURE_BUNDLE_SOURCE_CHANGED'):
            self.load()

    def test_wrong_commit_is_refused(self):
        self.manifest(lambda m:m.__setitem__('revision','0'*40))
        with self.assertRaisesRegex(ValueError,'SIGNATURE_BUNDLE_BINDING_REFUSED'):
            self.load()

    def test_symlink_is_refused(self):
        p=self.bundle/'signature.css';p.unlink();p.symlink_to('/etc/passwd')
        with self.assertRaisesRegex(ValueError,'SIGNATURE_ASSET_LINK_REFUSED'):
            self.load()

    def test_extra_resource_is_refused(self):
        (self.bundle/'unexpected.js').write_text('fixture')
        with self.assertRaisesRegex(ValueError,'SIGNATURE_BUNDLE_FILES_REFUSED'):
            self.load()

    def test_conversion_of_another_font_is_refused(self):
        self.manifest(lambda m:m['conversion'].__setitem__('source_sha256','0'*64))
        with self.assertRaisesRegex(ValueError,'SIGNATURE_CONVERSION_NOT_BOUND'):
            self.load()

    def test_integer_cannot_claim_regeneration_success(self):
        self.manifest(lambda m:m['regeneration'].__setitem__('regeneration_verified',1))
        with self.assertRaisesRegex(ValueError,'SIGNATURE_REGENERATION_NOT_VERIFIED'):
            self.load()


if __name__=='__main__':
    unittest.main()
