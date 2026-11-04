"""Run against genuinely regenerated WOFF2, including matching-but-invalid fonts.

SIGNATURE_CAPTURE and SIGNATURE_GENERATED select operator-owned test fixtures.
No production path is read or changed.
"""
import os
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from fontTools.ttLib import TTFont
import verify_generated as V


class Regeneration(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source, self.generated = self.root/'source', self.root/'generated'
        shutil.copytree(os.environ['SIGNATURE_CAPTURE'], self.source)
        shutil.copytree(os.environ['SIGNATURE_GENERATED'], self.generated)
        # copytree preserves the Nix store's read-only modes. Mutate only these
        # disposable copies, never the captured inputs or the store output.
        for path in self.root.rglob('*'):
            path.chmod(0o700 if path.is_dir() else 0o600)

    def verify(self):
        return V.verify(self.source, self.generated)

    def matching_modified_font(self, modify):
        path = self.generated/'web/MrJamSignature.woff2'
        with TTFont(path, recalcTimestamp=False) as font:
            modify(font)
            font.save(path)
        shutil.copyfile(path, self.source/'web/MrJamSignature.woff2')

    def test_reference_regeneration_is_exact(self):
        result = self.verify()
        self.assertTrue(result['regeneration_verified'])
        self.assertTrue(result['font_and_css_bytes_exact'])
        self.assertFalse(result['deployment_authorized'])

    def test_altered_candidate_font_is_refused(self):
        path = self.source/'web/EchoPoint.woff2'
        raw = bytearray(path.read_bytes()); raw[-1] ^= 1; path.write_bytes(raw)
        with self.assertRaisesRegex(ValueError, 'SIGNATURE_REGENERATION_MISMATCH'):
            self.verify()

    def test_altered_candidate_css_is_refused(self):
        with (self.source/'web/signature.css').open('ab') as stream:
            stream.write(b'\n.mrjam{display:none}\n')
        with self.assertRaisesRegex(ValueError, 'SIGNATURE_REGENERATION_MISMATCH'):
            self.verify()

    def test_matching_font_with_extra_unicode_is_refused(self):
        def modify(font):
            for table in font['cmap'].tables:
                if table.isUnicode():
                    table.cmap[ord('x')] = table.cmap[ord('M')]
        self.matching_modified_font(modify)
        with self.assertRaisesRegex(ValueError, 'SIGNATURE_UNICODE_REFUSED'):
            self.verify()

    def test_matching_font_with_changed_palette_contract_is_refused(self):
        self.matching_modified_font(lambda font: font['CPAL'].palettes.pop())
        with self.assertRaisesRegex(ValueError, 'SIGNATURE_COLOUR_CONTRACT_REFUSED'):
            self.verify()

    def test_missing_regenerated_font_is_refused(self):
        (self.generated/'web/EchoPoint.woff2').unlink()
        with self.assertRaisesRegex(ValueError, 'SIGNATURE_GENERATED_FILE_REFUSED'):
            self.verify()

    def test_geometry_number_format_is_not_a_geometry_change(self):
        self.assertEqual(V.geometry(b'{"x":-10}'), V.geometry(b'{"x":-10.0}'))

    def test_geometry_change_is_refused(self):
        path = self.source/'web/geometry.json'
        data = json.loads(path.read_bytes()); data['width_em'] += 0.001
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'SIGNATURE_REGENERATION_MISMATCH'):
            self.verify()

    def test_geometry_rejects_boolean_duplicate_and_nonfinite(self):
        for raw in (b'{"x":true}', b'{"x":1,"x":1}', b'{"x":NaN}', b'{"x":Infinity}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                V.geometry(raw)


if __name__ == '__main__':
    unittest.main()
