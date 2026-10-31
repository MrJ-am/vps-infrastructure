import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
OPERATIONS = ROOT.parent
sys.path.insert(0, str(OPERATIONS / "bootstrap-observation"))
sys.path.insert(0, str(OPERATIONS / "probes/adoption-v2"))


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


sys.modules["schema_core"] = module("schema_core", OPERATIONS / "probes/adoption-v2/validate_report.py")
probe = module("provenance_probe", ROOT / "probe/provenance_probe.py")
validator = module("provenance_validator", ROOT / "probe/validate_report.py")
launcher = module("provenance_launcher", ROOT / "observe.py")
original_launcher = module("original_launcher", OPERATIONS / "bootstrap-observation/observe.py")
GENERATION = "/nix/store/" + "a" * 32 + "-nixos-system-synthetic-26.05"
PROGRAM = Path("/nix/store/" + "b" * 32 + "-nixos-version/bin/nixos-version")
REVISION = "1" * 40
OTHER = "2" * 40
REPORT = {"schema_version": 1, "operation": "mrjam-system-provenance-v1",
          "authority": "unverified_observation", "generation_store_hash": "a" * 32,
          "configuration_revision": {"state": "observed", "code": "OK", "value": REVISION},
          "nixpkgs_revision": {"state": "unknown", "code": "UNAVAILABLE", "value": None},
          "state_version": None}


class Provenance(unittest.TestCase):
    def test_only_complete_hexadecimal_revision_is_returned(self):
        for raw in (REVISION.encode(), (REVISION + "\n").encode()):
            with patch.object(probe, "run", return_value=raw):
                self.assertEqual(probe.revision(str(PROGRAM), "--revision"),
                                 {"state": "observed", "code": "OK", "value": REVISION})
        for raw in (b"", b"SYNTHETIC_PRIVATE_MARKER", (REVISION + "-dirty\n").encode(),
                    (REVISION + "\n\n").encode(), b"f" * 39, b"f" * 41, b"F" * 40):
            with self.subTest(raw=raw), patch.object(probe, "run", return_value=raw):
                value = probe.revision(str(PROGRAM), "--revision")
                self.assertEqual(value, {"state": "unknown", "code": "INVALID_OUTPUT", "value": None})
                self.assertNotIn("SYNTHETIC_PRIVATE_MARKER", json.dumps(value))

    def test_failed_command_has_no_partial_success(self):
        with patch.object(probe, "run", side_effect=probe.Refused()):
            self.assertEqual(probe.revision(str(PROGRAM), "--revision"),
                             {"state": "unknown", "code": "UNAVAILABLE", "value": None})

    def collect_with(self, *, generations=None, mode=0o555, uid=0, gid=0, program=PROGRAM):
        value = types.SimpleNamespace(st_mode=stat.S_IFREG | mode, st_uid=uid, st_gid=gid)
        with patch.object(probe, "safe_readlink", side_effect=generations or [GENERATION, GENERATION]), \
                patch.object(probe.Path, "resolve", return_value=program) as resolve, \
                patch.object(probe.Path, "lstat", return_value=value), \
                patch.object(probe, "run", side_effect=[(REVISION + "\n").encode(), (OTHER + "\n").encode()]) as run:
            result = probe.collect()
            self.assertEqual(resolve.call_args.kwargs, {"strict": True})
            self.assertEqual([call.args[0] for call in run.call_args_list],
                             [[str(PROGRAM), "--configuration-revision"], [str(PROGRAM), "--revision"]])
            for call in run.call_args_list:
                self.assertEqual(call.kwargs["limit"], 64)
                self.assertEqual(call.kwargs["seconds"], 2)
                self.assertEqual(call.kwargs["environment"]["PATH"], "/no-path")
            return result

    def test_two_fixed_queries_and_stable_generation(self):
        result = self.collect_with()
        self.assertEqual(result["configuration_revision"]["value"], REVISION)
        self.assertEqual(result["nixpkgs_revision"]["value"], OTHER)
        self.assertEqual(result["generation_store_hash"], "a" * 32)
        self.assertIsNone(result["state_version"])
        validator.validate(json.dumps(result).encode())

    def test_generation_change_refuses_entire_report(self):
        with self.assertRaises(probe.Refused):
            self.collect_with(generations=[GENERATION, GENERATION + "-changed"])

    def test_unsafe_program_is_never_executed(self):
        for arguments in ({"mode": 0o577}, {"mode": 0o444}, {"uid": 1000}, {"gid": 1000},
                          {"program": Path("/tmp/arbitrary")},
                          {"program": Path("/nix/store/" + "b" * 32 + "-version/bin/sh")}):
            with self.subTest(arguments=arguments), self.assertRaises(probe.Refused):
                self.collect_with(**arguments)

    def test_root_or_arguments_are_refused_before_observation(self):
        for args, uid in ((["probe", "sh"], 1000), (["probe"], 0)):
            with patch.object(sys, "argv", args), patch.object(os, "getuid", return_value=uid), \
                    patch.object(probe, "collect") as collect, patch.object(sys, "stdout", io.StringIO()) as output:
                self.assertEqual(probe.main(), 65)
                collect.assert_not_called()
                self.assertEqual(output.getvalue(), "")

    def test_closed_report_accepts_observed_and_unknown(self):
        self.assertEqual(validator.validate(json.dumps(REPORT).encode()), REPORT)
        altered = copy.deepcopy(REPORT)
        altered["configuration_revision"] = {"state": "unknown", "code": "INVALID_OUTPUT", "value": None}
        self.assertEqual(validator.validate(json.dumps(altered).encode()), altered)

    def test_fields_types_authority_and_state_version_cannot_be_extended(self):
        mutations = [("extra", "SYNTHETIC_PRIVATE_MARKER"), ("schema_version", True),
                     ("authority", "verified"), ("state_version", "26.05"),
                     ("operation", "mrjam-inventory-adoption-v2"), ("generation_store_hash", "e" * 32)]
        for key, value in mutations:
            altered = dict(REPORT, **{key: value})
            with self.subTest(key=key), self.assertRaises(ValueError):
                validator.validate(json.dumps(altered).encode())

    def test_observed_revision_requires_exact_value_and_state(self):
        for item in ({"state": "unknown", "code": "UNAVAILABLE", "value": REVISION},
                     {"state": "observed", "code": "OK", "value": None},
                     {"state": "observed", "code": "OK", "value": "SYNTHETIC_PRIVATE_MARKER"}):
            with self.subTest(item=item), self.assertRaises(ValueError):
                validator.validate(json.dumps(dict(REPORT, configuration_revision=item)).encode())

    def test_duplicates_floats_and_oversized_documents_are_refused(self):
        raw = json.dumps(REPORT).encode()
        for value in (raw.replace(b'"schema_version": 1', b'"schema_version": 1, "schema_version": 1'),
                      raw.replace(b'"schema_version": 1', b'"schema_version": 1.0'),
                      raw + b'x', b' ' * 2049 + raw):
            with self.subTest(length=len(value)), self.assertRaises(ValueError):
                validator.validate(value)

    def test_schema_substitution_link_and_fifo_are_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            source = folder / "source"
            source.write_bytes((ROOT / "probe/provenance.schema.json").read_bytes())
            path = folder / "provenance.schema.json"
            with patch.object(validator, "__file__", str(folder / "validate_report.py")):
                path.symlink_to(source)
                with self.assertRaises(OSError): validator.schema()
                path.unlink()
                os.mkfifo(path)
                with self.assertRaises(ValueError): validator.schema()
                path.unlink()
                path.write_bytes(b'{}')
                with self.assertRaises(ValueError): validator.schema()

    def test_bootstrap_keeps_qualified_sandbox_and_fixed_new_unit(self):
        self.assertEqual(launcher.PROPERTIES, original_launcher.PROPERTIES)
        command = launcher.command({"python": "/nix/store/python/bin/python3", "systemd_run": "/nix/store/systemd/bin/systemd-run"})
        self.assertIn("--unit=mrjam-observe-provenance", command)
        self.assertEqual(command[command.index("--") + 1:], ["/nix/store/python/bin/python3", "-I", "-S", str(ROOT / "collect.py")])
        with self.assertRaises(probe.Refused): launcher.immutable_entry()

    def test_bootstrap_refuses_caller_input_without_echo(self):
        with patch.object(sys, "argv", ["observe", "SYNTHETIC_PRIVATE_MARKER"]), \
                patch.object(launcher, "run") as run, patch.object(sys, "stdout", io.StringIO()) as out, \
                patch.object(sys, "stderr", io.StringIO()) as err:
            self.assertEqual(launcher.main(), 65)
            run.assert_not_called()
            self.assertEqual(out.getvalue(), "")
            self.assertEqual(err.getvalue(), "PROVENANCE_OBSERVATION_FAILED\n")


if __name__ == "__main__":
    unittest.main()
