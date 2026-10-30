"""Only synthetic reports and local reviewed source files enter this suite."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from test_adoption import report

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("adoption_filter", HERE / "validate_report.py")
filtre = importlib.util.module_from_spec(spec)
spec.loader.exec_module(filtre)


class FilterTest(unittest.TestCase):
    def setUp(self):
        self.schema = filtre.load_schema()
        self.report = report()

    def execute(self, raw, args=(), directory=HERE):
        return subprocess.run([sys.executable, "-I", "-S", str(directory / "validate_report.py"), *args],
                              input=raw, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=8, check=False)

    def assert_rejected(self, result, code="INVALID_REPORT"):
        self.assertEqual(result.returncode, 65)
        self.assertEqual(result.stderr, b"")
        self.assertEqual(json.loads(result.stdout), {"status": "rejected", "code": code})

    def test_valid_report_normalized_and_authority_unchanged(self):
        result = self.execute(json.dumps(self.report).encode())
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, b"")
        self.assertEqual(json.loads(result.stdout), self.report)
        self.assertEqual(json.loads(result.stdout)["authority"], "unverified_observation")

    def test_valid_unknowns_are_not_promoted(self):
        for item in self.report["paths"].values():
            item.update(state="unknown", code="UNAVAILABLE", type_matches=None,
                        owner_matches=None, group_matches=None, mode_matches=None)
        result = self.execute(json.dumps(self.report).encode())
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout), self.report)

    def test_unknown_property_cannot_disclose_content(self):
        for location in [self.report, self.report["account"], self.report["paths"]["work"], self.report["generation"]["current"]]:
            location["synthetic_secret"] = "DO_NOT_ECHO"
            result = self.execute(json.dumps(self.report).encode())
            self.assert_rejected(result)
            self.assertNotIn(b"DO_NOT_ECHO", result.stdout)
            del location["synthetic_secret"]

    def test_uid_type_and_range_are_strict(self):
        for value in [True, False, 0, -1, 2**31, "601", 601.0, None]:
            with self.subTest(value=value):
                self.report["account"]["uid"] = value
                self.assertFalse(filtre.valid(self.report, self.schema))

    def test_typed_literal_version(self):
        self.report["schema_version"] = True
        self.assertFalse(filtre.valid(self.report, self.schema))

    def test_closed_codes_and_hash_shape(self):
        for value in ["SYNTHETIC_HOSTNAME", "x" * 33, "e" * 32, "0" * 31 + "\n"]:
            self.report["generation"]["current"]["store_hash"] = value
            self.assertFalse(filtre.valid(self.report, self.schema))

    def test_cross_field_generation_consistency(self):
        self.report["generation"]["profile"]["matches_current"] = False
        self.assertFalse(filtre.valid(self.report, self.schema))
        self.report["generation"]["profile"]["matches_current"] = None
        self.assertFalse(filtre.valid(self.report, self.schema))

    def test_observed_root_metadata_cannot_be_null(self):
        self.report["paths"]["login"]["owner_matches"] = None
        self.assertFalse(filtre.valid(self.report, self.schema))

    def test_work_ownership_requires_observed_account(self):
        self.report["account"] = {key: None for key in self.report["account"]}
        self.report["account"].update(state="absent", code="NOT_FOUND")
        self.assertFalse(filtre.valid(self.report, self.schema))
        self.report["paths"]["work"].update(owner_matches=None, group_matches=None)
        self.assertTrue(filtre.valid(self.report, self.schema))

    def test_no_success_with_mixed_absence_values(self):
        self.report["generation"]["current"].update(state="absent", code="NOT_FOUND")
        self.assertFalse(filtre.valid(self.report, self.schema))

    def test_reject_duplicates_multiple_documents_floats_nonfinite_and_nonobject(self):
        for raw in [b'{"schema_version":1,"schema_version":1}', b'{} {}', b'{"x":1.0}',
                    b'{"x":NaN}', b'{"x":Infinity}', b'["DO_NOT_ECHO"]', b'null', b'\xff']:
            with self.subTest(raw=raw):
                self.assert_rejected(self.execute(raw))

    def test_oversized_or_deep_input_has_no_partial_return(self):
        for raw in [b" " * (filtre.MAX_INPUT + 1), b"[" * 2000 + b"0" + b"]" * 2000]:
            self.assert_rejected(self.execute(raw))

    def test_arguments_are_refused(self):
        self.assert_rejected(self.execute(b"", ["--schema", "/etc/shadow"]), "UNSUPPORTED_ARGUMENTS")

    def test_schema_tampering_or_symlink_is_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "validate_report.py").write_bytes((HERE / "validate_report.py").read_bytes())
            (directory / "adoption.schema.json").write_bytes(b'{"SYNTHETIC_SECRET":"DO_NOT_ECHO"}')
            self.assert_rejected(self.execute(json.dumps(self.report).encode(), directory=directory))
            (directory / "adoption.schema.json").unlink()
            (directory / "adoption.schema.json").symlink_to(HERE / "adoption.schema.json")
            self.assert_rejected(self.execute(json.dumps(self.report).encode(), directory=directory))

    def test_schema_pin_matches_exact_source_bytes(self):
        self.assertEqual(hashlib.sha256((HERE / "adoption.schema.json").read_bytes()).hexdigest(), filtre.SCHEMA_SHA256)

    def test_stalled_input_is_bounded(self):
        process = subprocess.Popen([sys.executable, "-I", "-S", str(HERE / "validate_report.py")],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            process.wait(timeout=8)
            output = process.stdout.read()
            errors = process.stderr.read()
            self.assertEqual(process.returncode, 65)
            self.assertEqual(errors, b"")
            self.assertEqual(json.loads(output), {"status": "rejected", "code": "INVALID_REPORT"})
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            process.stdin.close()
            process.stdout.close()
            process.stderr.close()


if __name__ == "__main__":
    unittest.main()
