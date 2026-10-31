import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "export_review.py"
spec = importlib.util.spec_from_file_location("export_review", MODULE_PATH)
export = importlib.util.module_from_spec(spec)
spec.loader.exec_module(export)


class ReviewExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="mrjam-review-test-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / "selection.json"
        self.proof = self.root / "proof.json"
        self.proof.write_text('{"synthetic":true}\n')
        self.package = "/nix/store/" + "0" * 32 + "-invented"
        self.hash = "sha256-" + "A" * 43 + "="
        self.selection = {
            "schema_version": 1, "scope": "public-review-only", "production_authorized": False,
            "roots": {self.package: self.hash},
            "evidence_sha256": {"fixture/proof.json": hashlib.sha256(self.proof.read_bytes()).hexdigest()},
            "limits": {"max_closure_paths": 64, "max_total_nar_bytes": 268435456},
            "not_included": ["Production"], "notes": ["Invented test only"],
        }
        self.closure = {self.package: {"nar_hash": self.hash, "nar_size": 64, "references": []}}

    def load(self):
        self.path.write_text(json.dumps(self.selection))
        return export.load_selection(self.path, export.checksum(self.path), {"fixture": self.root})

    def test_synthetic_selection_and_closed_closure(self):
        selected, evidence = self.load()
        self.assertEqual(evidence["evidence/fixture/proof.json"], self.proof.read_bytes())
        export.validate_closure(selected, self.closure)

    def test_mismatched_selection_and_evidence_refused(self):
        self.load()
        with self.assertRaisesRegex(export.Refused, "SELECTION_HASH_MISMATCH"):
            export.load_selection(self.path, "0" * 64, {"fixture": self.root})
        self.proof.write_text('changed')
        with self.assertRaisesRegex(export.Refused, "EVIDENCE_HASH_MISMATCH"):
            self.load()

    def test_duplicate_json_refused(self):
        with self.assertRaisesRegex(export.Refused, "DUPLICATE_JSON_KEY"):
            json.loads('{"a":1,"a":2}', object_pairs_hook=export.unique)

    def test_production_scope_and_traversal_refused(self):
        self.selection["production_authorized"] = True
        with self.assertRaisesRegex(export.Refused, "REVIEW_SCOPE_REQUIRED"):
            self.load()
        self.selection["production_authorized"] = False
        self.selection["evidence_sha256"] = {"fixture/../proof.json": "0" * 64}
        with self.assertRaisesRegex(export.Refused, "EVIDENCE_PATH_REFUSED"):
            self.load()

    def test_links_and_fifo_do_not_read_or_block(self):
        alias = self.root / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(export.Refused, "AMBIGUOUS_PUBLIC_PATH"):
            export.public_bytes(alias / "proof.json")
        export.os.mkfifo(self.root / "fifo")
        with self.assertRaisesRegex(export.Refused, "PUBLIC_FILE_REFUSED"):
            export.public_bytes(self.root / "fifo")

    def test_incomplete_changed_and_oversized_closures_refused(self):
        invalid = copy.deepcopy(self.closure)
        invalid[self.package]["references"] = [self.package + "-missing"]
        with self.assertRaisesRegex(export.Refused, "INCOMPLETE_CLOSURE"):
            export.validate_closure(self.selection, invalid)
        invalid = copy.deepcopy(self.closure)
        invalid[self.package]["nar_hash"] = "sha256-" + "B" * 43 + "="
        with self.assertRaisesRegex(export.Refused, "ROOT_NAR_MISMATCH"):
            export.validate_closure(self.selection, invalid)
        invalid[self.package]["nar_size"] = 268435457
        with self.assertRaisesRegex(export.Refused, "CLOSURE_BUDGET"):
            export.validate_closure(self.selection, invalid)

    def test_optimized_python_keeps_refusals(self):
        code = "import runpy; m=runpy.run_path(%r); m['require'](False,'REFUSAL_RETAINED')" % str(MODULE_PATH)
        result = subprocess.run([sys.executable, "-O", "-c", code], capture_output=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"REFUSAL_RETAINED", result.stderr)

    def test_only_versioned_selections_can_be_exported(self):
        self.assertEqual(export.selection_reference('platform-20261031'),
                         (export.SELECTION, '17944c0c802082f9650493c1da8122357a15fc676d2e7fe68ebe17d5fd20f580'))
        for unknown in ('/arbitrary/path.json', '../selection', 'production', ''):
            with self.subTest(name=unknown), self.assertRaisesRegex(export.Refused, 'UNKNOWN_REVIEW_SELECTION'):
                export.selection_reference(unknown)


if __name__ == "__main__":
    unittest.main()
