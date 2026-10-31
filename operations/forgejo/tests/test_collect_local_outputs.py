"""Local metadata decoding only; no Docker, artifact export or production read."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('collect_local_outputs', Path(__file__).with_name('collect_local_outputs.py'))
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)


class QualificationMetadata(unittest.TestCase):
    def test_fractional_elapsed_time_is_metadata_only(self):
        value = collector.qualification_json(b'{"duration_seconds":1157.092,"fixture_uid":59990}')
        self.assertEqual(str(value['duration_seconds']), '1157.092')
        self.assertEqual(value['fixture_uid'], 59990)

    def test_fractional_security_field_is_refused(self):
        for raw in (b'{"duration_seconds":1.2,"fixture_uid":59990.0}',
                    b'{"duration_seconds":1.2,"artifacts":[{"bytes":42.0}]}'):
            with self.assertRaises(collector.pack.Refused):
                collector.qualification_json(raw)

    def test_duplicate_fields_are_refused(self):
        with self.assertRaises(collector.pack.Refused):
            collector.qualification_json(b'{"duration_seconds":1,"duration_seconds":2}')

    def test_unbounded_missing_and_nonfinite_elapsed_time_are_refused(self):
        for raw in (b'{}', b'{"duration_seconds":true}', b'{"duration_seconds":0}',
                    b'{"duration_seconds":1861}', b'{"duration_seconds":NaN}',
                    b'{"duration_seconds":1e100000}', b'{"duration_seconds":"1.2"}'):
            with self.assertRaises(collector.pack.Refused):
                collector.qualification_json(raw)

    def test_artifact_lock_parser_still_refuses_fractional_numbers(self):
        with self.assertRaises(collector.pack.Refused):
            collector.pack.parse(b'{"bytes":42.0}')


if __name__ == '__main__':
    unittest.main()
