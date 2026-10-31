"""Invented bytes only: these tests qualify packaging refusals, not applications."""
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "import_qualified.py"
SPEC = importlib.util.spec_from_file_location("qualified_import", SCRIPT)
importer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(importer)


def archive(extra=()):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        for name, kind in [(name + "/index.html", tarfile.REGTYPE) for name in sorted(importer.FRONTENDS)] + list(extra):
            member = tarfile.TarInfo(name)
            member.type, member.mode, member.mtime = kind, 0o444, 0
            data = b"INVENTED_PUBLIC_ASSET"
            member.size = len(data) if kind == tarfile.REGTYPE else 0
            member.linkname = "/etc/INVENTED_ONLY" if kind in (tarfile.SYMTYPE, tarfile.LNKTYPE) else ""
            tar.addfile(member, io.BytesIO(data) if member.size else None)
    return output.getvalue()


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.inputs = self.root / "inputs"
        self.inputs.mkdir()
        # Deliberately not executable. No test claims this fixture is Rust.
        elf = bytearray(64)
        elf[:7], elf[18:20] = b"\x7fELF\x02\x01\x01", (62).to_bytes(2, "little")
        (self.inputs / "server").write_bytes(elf)
        (self.inputs / "frontend.tar").write_bytes(archive())
        steps = {"complete-trees-submodules-and-locked-tools", "rust-format", "rust-clippy-all-features",
                 "rust-http-postgres-rls-tls-tests", "rust-release", "independent-http-release-bytes", "elm-rules-208"}
        steps |= {prefix + name for name in importer.FRONTENDS for prefix in ("elm-compile-", "elm-review-prepare-", "elm-review-", "frontend-resource-closure-")}
        self.receipt = {"schema_version": 1, "decision": "passed", "authority": "local-verifier-content-receipt",
                        "independent_adoption_established": False, "production_authorized": False,
                        "proposal_sha256": "a" * 64, "rules_revision": "b" * 40, "policy_sha256": "c" * 64,
                        "steps": [{"name": name, "status": "passed"} for name in sorted(steps)],
                        "sources": [], "artifacts": [], "not_established": ["INVENTED TEST FIXTURE"]}
        self.lock_path = self.root / "lock.json"
        self.refresh_fixture_pins()

    def refresh_fixture_pins(self):
        """Construct invented cases only; never used to repair observed outputs."""
        files = {name: {"bytes": (self.inputs / name).stat().st_size,
                        "sha256": importer.sha((self.inputs / name).read_bytes())} for name in ("server", "frontend.tar")}
        self.receipt["artifacts"] = [{"name": name, **pin} for name, pin in files.items()]
        (self.inputs / "verification.json").write_text(json.dumps(self.receipt))
        data = (self.inputs / "verification.json").read_bytes()
        files["verification.json"] = {"bytes": len(data), "sha256": importer.sha(data)}
        self.lock = {"schema_version": 1, "kind": "mrjam-qualified-artifact-import", "files": files,
                     **{key: self.receipt[key] for key in ("proposal_sha256", "rules_revision", "policy_sha256")}}
        self.lock_path.write_text(json.dumps(self.lock))
        self.expected = importer.sha(self.lock_path.read_bytes())

    def run_import(self):
        return importer.install(self.inputs, self.lock_path, self.expected, self.root / "output")

    def test_bytes_and_modes_preserved_without_execution(self):
        result = self.run_import()
        self.assertFalse(result["production_authorized"])
        self.assertFalse(result["independent_adoption_established"])
        self.assertEqual(result["frontend_files"], 7)
        self.assertEqual((self.root / "output/bin/mrjam-server").read_bytes(), (self.inputs / "server").read_bytes())
        self.assertEqual((self.root / "output/bin/mrjam-server").stat().st_mode & 0o777, 0o555)
        for name in ("frontend.tar", "verification.json"):
            self.assertEqual((self.root / "output/share/mrjam" / name).read_bytes(), (self.inputs / name).read_bytes())
        self.assertEqual((self.root / "output/share/mrjam/import.lock.json").read_bytes(), self.lock_path.read_bytes())

    def test_equal_length_payload_substitution_refused(self):
        p = self.inputs / "server"
        data = bytearray(p.read_bytes()); data[-1] = 42; p.write_bytes(data)
        with self.assertRaisesRegex(importer.Refused, "ARTIFACT_HASH_MISMATCH"):
            self.run_import()
        self.assertFalse((self.root / "output").exists())

    def test_lock_substitution_does_not_repair_pin(self):
        self.lock["rules_revision"] = "d" * 40
        self.lock_path.write_text(json.dumps(self.lock))
        with self.assertRaisesRegex(importer.Refused, "LOCK_HASH_MISMATCH"):
            self.run_import()

    def test_receipt_binding_checked_after_content_hash(self):
        self.lock["proposal_sha256"] = "d" * 64
        self.lock_path.write_text(json.dumps(self.lock))
        self.expected = importer.sha(self.lock_path.read_bytes())
        with self.assertRaisesRegex(importer.Refused, "RECEIPT_BINDING_REFUSED"):
            self.run_import()

    def test_failed_or_missing_check_refused(self):
        original = copy.deepcopy(self.receipt)
        for change in ("failed", "missing", "duplicate"):
            with self.subTest(change=change):
                self.receipt = copy.deepcopy(original)
                if change == "failed": self.receipt["steps"][0]["status"] = "failed"
                elif change == "missing": self.receipt["steps"].pop(0)
                else: self.receipt["steps"].append(self.receipt["steps"][0])
                self.refresh_fixture_pins()
                with self.assertRaises(importer.Refused): self.run_import()

    def test_no_self_claimed_production_authority(self):
        self.receipt["production_authorized"] = True
        self.refresh_fixture_pins()
        with self.assertRaisesRegex(importer.Refused, "RECEIPT_SCOPE_REFUSED"):
            self.run_import()

    def test_archive_links_paths_duplicates_special_files_refused(self):
        cases = [("vision/link", tarfile.SYMTYPE), ("vision/link", tarfile.LNKTYPE),
                 ("vision/fifo", tarfile.FIFOTYPE), ("vision/../../escape", tarfile.REGTYPE),
                 ("/vision/escape", tarfile.REGTYPE), ("vision//escape", tarfile.REGTYPE),
                 ("vision/index.html", tarfile.REGTYPE), ("unknown/file", tarfile.REGTYPE),
                 ("vision/index.html/child", tarfile.REGTYPE)]
        for entry in cases:
            with self.subTest(entry=entry):
                (self.inputs / "frontend.tar").write_bytes(archive([entry]))
                self.refresh_fixture_pins()
                with self.assertRaises(importer.Refused): self.run_import()
                self.assertFalse((self.root / "output").exists())

    def test_special_input_and_ancestor_link_refused(self):
        p = self.inputs / "server"
        p.unlink(); os.mkfifo(p)
        with self.assertRaises(importer.Refused): self.run_import()
        p.unlink(); p.symlink_to("verification.json")
        with self.assertRaises(OSError): self.run_import()
        alias = self.root / "alias"; alias.symlink_to(self.inputs, target_is_directory=True)
        with self.assertRaises(OSError): importer.read_file(alias / "verification.json", 65536)

    def test_reuse_existing_output_refused(self):
        self.run_import()
        with self.assertRaisesRegex(importer.Refused, "NEW_OUTPUT_REQUIRED"):
            self.run_import()

    def test_duplicate_json_field_and_error_do_not_echo(self):
        with self.assertRaisesRegex(importer.Refused, "DUPLICATE_FIELD"):
            importer.parse(b'{"a":1,"a":2}')
        result = subprocess.run([sys.executable, "-I", "-S", str(SCRIPT), "INVENTED_PRIVATE_MARKER"], capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn(b"INVENTED_PRIVATE_MARKER", result.stdout + result.stderr)
        self.assertEqual(result.stderr, b"")


if __name__ == "__main__":
    unittest.main()
