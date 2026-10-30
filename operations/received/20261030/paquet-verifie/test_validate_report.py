"""Acceptance examples for the report boundary; no host or service is probed."""

import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest

import validate_report


MARKER = "SYNTHETIC_PRIVATE_MARKER_DO_NOT_EMIT"
ROOT = Path(__file__).resolve().parent
SCHEMA = ROOT.joinpath("inventory.schema.json").read_bytes()


def synthetic_report():
    """Declared v1 contract examples, independent of inventory.collect()."""
    return {
        "schema_version": 1,
        "scope": "local_read_only_metadata",
        "authority": "unverified_observation",
        "resources": {
            "logical_cpu_count": {"status": "ok", "value": 4},
            "memory_total_bytes": {"status": "ok", "value": 8_589_934_592},
            "root_filesystem_total_bytes": {"status": "ok", "value": 34_359_738_368},
            "root_filesystem_available_bytes": {"status": "ok", "value": 17_179_869_184},
        },
        "isolation": {
            "kvm": {"status": "ok", "device_present": False},
            "user_namespace_limit_nonzero": {"status": "ok", "enabled": True},
            "unprivileged_user_namespace_switch": {"status": "unknown", "code": "UNAVAILABLE"},
        },
        "versions": {
            "nixos": {"status": "ok", "release_core": [26, 5], "exact_build": "not_reported"},
            "nix": {"status": "ok", "release_core": [2, 31, 1], "exact_build": "not_reported"},
            "forgejo": {"status": "ok", "release_core": [12, 0, 3], "exact_build": "not_reported"},
            "forgejo_runner": {"status": "unknown", "code": "UNAVAILABLE"},
            "postgresql": {"status": "ok", "release_core": [17, 11], "exact_build": "not_reported"},
            "kanidm": {"status": "unknown", "code": "UNAVAILABLE"},
        },
        "services": {
            "forgejo": {"status": "ok", "load_state": "loaded", "active_state": "active"},
            "postgresql": {"status": "ok", "load_state": "loaded", "active_state": "active"},
            "kanidm": {"status": "ok", "load_state": "not-found", "active_state": "inactive"},
            "nginx": {"status": "ok", "load_state": "loaded", "active_state": "active"},
            "mrjam_metier": {"status": "unknown", "code": "UNAVAILABLE"},
            "nextcloud_php_pool": {"status": "unknown", "code": "UNAVAILABLE"},
        },
    }


class ReportBoundaryTests(unittest.TestCase):
    def run_filter(self, raw, *args):
        result = subprocess.run(
            [sys.executable, "-I", "-S", str(ROOT / "validate_report.py"), *args],
            input=raw, capture_output=True, timeout=5, check=False,
        )
        self.assertEqual(result.stderr, b"")
        self.assertNotIn(MARKER.encode(), result.stdout)
        return result.returncode, json.loads(result.stdout)

    def reject(self, report):
        raw = report if isinstance(report, bytes) else json.dumps(report).encode()
        self.assertEqual(self.run_filter(raw), (1, {"status": "rejected", "code": "INVALID_REPORT"}))

    def test_accepts_declared_observation_without_promoting_authority(self):
        report = synthetic_report()
        self.assertEqual(self.run_filter(json.dumps(report).encode()), (0, report))

    def test_unknown_checks_remain_unknown(self):
        report = synthetic_report()
        for section in ("resources", "isolation", "versions", "services"):
            for key in report[section]:
                report[section][key] = {"status": "unknown", "code": "UNAVAILABLE"}
        self.assertEqual(self.run_filter(json.dumps(report).encode()), (0, report))

    def test_probe_error_is_filtered_but_never_success(self):
        report = {"schema_version": 1, "status": "error", "code": "INTERNAL_ERROR"}
        self.assertEqual(self.run_filter(json.dumps(report).encode()), (1, report))

    def test_rejects_unknown_fields_at_every_boundary(self):
        report = synthetic_report()
        for path in ((), ("resources",), ("resources", "logical_cpu_count"), ("isolation", "kvm"), ("versions", "forgejo"), ("services", "forgejo")):
            with self.subTest(path=path):
                mutant = copy.deepcopy(report)
                target = mutant
                for name in path:
                    target = target[name]
                target["private"] = MARKER
                self.reject(mutant)

    def test_rejects_missing_checks_and_forged_authority(self):
        report = synthetic_report()
        del report["versions"]["kanidm"]
        self.reject(report)
        report = synthetic_report()
        report["authority"] = "verified"
        self.reject(report)

    def test_numeric_bounds_types_and_enumerations_are_closed(self):
        for value in (True, -1, 1 << 63, 1.0, MARKER, None, [1]):
            with self.subTest(value=value):
                report = synthetic_report()
                report["resources"]["logical_cpu_count"]["value"] = value
                self.reject(report)
        report = synthetic_report()
        report["schema_version"] = True
        self.reject(report)
        report = synthetic_report()
        report["isolation"]["kvm"]["device_present"] = 1
        self.reject(report)
        report = synthetic_report()
        report["services"]["forgejo"]["active_state"] = MARKER
        self.reject(report)

    def test_versions_cannot_carry_build_labels_or_unbounded_parts(self):
        for core in ([1], [1, 2, 3, 4, 5], [1, 10_000], [True, 1], [1, MARKER]):
            report = synthetic_report()
            report["versions"]["forgejo"]["release_core"] = core
            self.reject(report)
        report = synthetic_report()
        report["versions"]["forgejo"]["exact_build"] = MARKER
        self.reject(report)

    def test_rejects_ambiguous_json_and_non_json_numbers(self):
        raw = json.dumps(synthetic_report()).encode()
        for mutant in (raw.replace(b'"schema_version": 1', b'"schema_version": 1,"schema_version": 1'), raw + raw, b'{"value":NaN}', b'{"value":Infinity}', b'\xff', b'', b'[' * 2000):
            self.reject(mutant)

    def test_rejects_oversized_input_before_parsing(self):
        self.reject(b' ' * 16_385 + MARKER.encode())
        self.reject(b'{"value":' + b'9' * 1_000 + b'}')

    def test_no_generic_argument_or_echo(self):
        self.assertEqual(self.run_filter(b'', "--schema", MARKER), (2, {"status": "rejected", "code": "UNSUPPORTED_ARGUMENTS"}))

    def test_schema_cannot_be_replaced_with_permissive_policy(self):
        raw = json.dumps(synthetic_report()).encode()
        with self.assertRaises(validate_report.InvalidReport):
            validate_report.validate(raw, b'{}')
        with self.assertRaises(validate_report.InvalidReport):
            validate_report.validate(raw, SCHEMA + b'\n')
        self.assertEqual(validate_report.validate(raw, SCHEMA), synthetic_report())


if __name__ == "__main__":
    unittest.main()
