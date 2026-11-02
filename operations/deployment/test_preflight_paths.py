import importlib.util
from pathlib import Path
import json
import os
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location("preflight_paths",Path(__file__).with_name("preflight_paths.py"))
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class ClosedPaths(unittest.TestCase):
    def test_exact_declared_catalog(self):
        path=Path(__file__).parents[1]/"hosts/mrjam-vps/candidate-metadata-paths.json"
        document=json.loads(path.read_text())
        expected={p for v in document.values() if isinstance(v,list) for p in v}
        self.assertEqual(set(m.PATHS),expected)
        self.assertEqual(len(m.PATHS),len(expected))

    def test_contents_and_size_do_not_escape(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"invented"
            p.write_text("SYNTHETIC_PRIVATE_VALUE")
            p.chmod(0o600)
            with patch("builtins.open",side_effect=AssertionError("No content read")):
                value=m.metadata(p)
            self.assertEqual(set(value),{"state","kind","uid","gid","mode"})
            self.assertNotIn("PRIVATE",json.dumps(value))

    def test_symlink_not_followed_missing_and_error_are_distinct(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"invented"
            self.assertEqual(m.metadata(p),{"state":"absent"})
            p.symlink_to("/never-open")
            self.assertEqual(m.metadata(p)["kind"],"symlink")
            with patch.object(os,"lstat",side_effect=PermissionError("PRIVATE")):
                self.assertEqual(m.metadata(p),{"state":"unknown"})


if __name__=="__main__":
    unittest.main()
