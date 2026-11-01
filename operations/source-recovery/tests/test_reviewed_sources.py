"""Synthetic transport contracts; no private source or VPS access."""
import hashlib
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

SOURCE = Path(__file__).resolve().parents[1] / "reviewed_sources.py"
spec = importlib.util.spec_from_file_location("reviewed_sources", SOURCE)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


class SourcesTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "reviewed"
        self.root.mkdir()
        self.content = b'{ ... }: { system.stateVersion = "24.11"; }\n'
        (self.root / "configuration.nix").write_bytes(self.content)
        self.value = {
            "schema_version": 1, "operation": "mrjam-reviewed-configuration-sources-v1",
            "authority": "human-reviewed-code-only-declaration", "target": "mrjam-vps",
            "entrypoint": "configuration.nix", "declared_state_version": {"value": None, "source": None},
            "declared_graph_complete": False, "generation_binding": "unverified",
            "files": [{"path": "configuration.nix", "bytes": len(self.content),
                       "sha256": hashlib.sha256(self.content).hexdigest(), "change": "unknown"}],
        }
        self.write_review()
        self.output = self.base / "sources.tar"

    def write_review(self):
        (self.root / "review.json").write_text(json.dumps(self.value, indent=2) + "\n")

    def refuse_pack(self, code=None):
        with self.assertRaises(tool.Refused) as error:
            tool.pack(self.root, self.output)
        if code:
            self.assertEqual(str(error.exception), code)
        self.assertFalse(self.output.exists())

    def test_deterministic_archive_and_independent_tar_inspection(self):
        result = tool.pack(self.root, self.output)
        other = self.base / "other.tar"
        os.utime(self.root / "configuration.nix", (123456, 123456))
        os.chmod(self.root / "configuration.nix", 0o755)
        tool.pack(self.root, other)
        self.assertEqual(self.output.read_bytes(), other.read_bytes())
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o600)
        self.assertEqual(tool.verify(self.output, result["sha256"]), result)
        self.assertFalse(result["production_ready"])
        self.assertFalse(result["confidentiality_verified_by_tool"])
        self.assertFalse(result["installed_generation_verified"])
        with tarfile.open(self.output) as archive:
            self.assertEqual(archive.getnames(), ["SHA256SUMS", "review.json", "source/configuration.nix"])
            self.assertEqual(archive.extractfile("source/configuration.nix").read(), self.content)
            review = archive.extractfile("review.json").read()
            self.assertIsNone(json.loads(review)["declared_state_version"]["value"])
            expected_sums = (hashlib.sha256(review).hexdigest() + "  review.json\n" +
                             hashlib.sha256(self.content).hexdigest() + "  source/configuration.nix\n")
            self.assertEqual(archive.extractfile("SHA256SUMS").read(), expected_sums.encode())

    def test_hash_mismatch_never_rewrites_manifest(self):
        original = (self.root / "review.json").read_bytes()
        (self.root / "configuration.nix").write_bytes(b"changed\n")
        self.refuse_pack("CONTENT_MISMATCH")
        self.assertEqual((self.root / "review.json").read_bytes(), original)

    def test_no_overwrite(self):
        self.output.write_bytes(b"existing artifact")
        with self.assertRaises(FileExistsError):
            tool.pack(self.root, self.output)
        self.assertEqual(self.output.read_bytes(), b"existing artifact")

    def test_unlisted_file_and_directory_refused_without_opening_contents(self):
        extra = self.root / "unreviewed.txt"
        extra.write_bytes(b"synthetic excluded sentinel")
        extra.chmod(0)
        self.refuse_pack("UNDECLARED_ENTRY")
        extra.unlink()
        (self.root / "unlisted").mkdir()
        self.refuse_pack("UNDECLARED_ENTRY")

    def test_traversal_absolute_hidden_and_ambiguous_paths_refused(self):
        for name in ("../outside.nix", "/etc/nixos/configuration.nix", "a/../x", "a//x", "a/./x",
                     ".git/config", "a/.hidden", "a\\b", "x\ny", "é.nix", "review.json", "x/"):
            with self.subTest(name=name):
                self.value["files"][0]["path"] = name
                self.value["entrypoint"] = name
                self.write_review()
                self.refuse_pack()

    def test_duplicate_json_key_and_duplicate_file_refused(self):
        path = self.root / "review.json"
        path.write_text('{"schema_version":1,"schema_version":1}')
        self.refuse_pack("DUPLICATE_JSON_KEY")
        self.value["files"].append(dict(self.value["files"][0]))
        self.write_review()
        self.refuse_pack("DUPLICATE_OR_RESERVED_PATH")

    def test_wrong_scope_or_approval_claim_refused(self):
        for field, bad in (("target", "spectre"), ("authority", "authenticated"),
                           ("generation_binding", "verified"), ("schema_version", True),
                           ("declared_graph_complete", "true")):
            with self.subTest(field=field):
                old = self.value[field]
                self.value[field] = bad
                self.write_review()
                self.refuse_pack()
                self.value[field] = old

    def test_state_version_requires_named_source_and_preserves_redaction(self):
        self.value["declared_state_version"] = {"value": "24.11", "source": "missing.nix"}
        self.write_review()
        self.refuse_pack("INVALID_STATE_VERSION_DECLARATION")
        self.value["declared_state_version"]["source"] = "configuration.nix"
        self.value["files"][0]["change"] = "redacted"
        self.write_review()
        result = tool.pack(self.root, self.output)
        self.assertEqual(result["files"], 1)
        with tarfile.open(self.output) as archive:
            value = json.load(archive.extractfile("review.json"))
            self.assertEqual(value["files"][0]["change"], "redacted")
            self.assertEqual(value["declared_state_version"]["value"], "24.11")

    def test_source_link_hardlink_fifo_refused(self):
        file = self.root / "configuration.nix"
        file.unlink()
        outside = self.base / "outside.nix"
        outside.write_bytes(self.content)
        file.symlink_to(outside)
        self.refuse_pack("REGULAR_SINGLE_LINK_REQUIRED")
        file.unlink()
        os.link(outside, file)
        self.refuse_pack("REGULAR_SINGLE_LINK_REQUIRED")
        file.unlink()
        os.mkfifo(file)
        self.refuse_pack("REGULAR_SINGLE_LINK_REQUIRED")

    def test_linked_root_or_parent_refused(self):
        linked = self.base / "link"
        linked.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(OSError):
            tool.pack(linked, self.output)
        parent = self.base / "linked-parent"
        parent.symlink_to(self.base, target_is_directory=True)
        with self.assertRaises(OSError):
            tool.pack(parent / "reviewed", self.output)

    def test_nested_directory_link_refused(self):
        outside = self.base / "outside"
        outside.mkdir()
        (outside / "module.nix").write_bytes(self.content)
        (self.root / "modules").symlink_to(outside, target_is_directory=True)
        self.value["files"].append(dict(self.value["files"][0], path="modules/module.nix"))
        self.write_review()
        self.refuse_pack("DIRECTORY_REQUIRED")

    def test_pack_and_verify_137_files(self):
        (self.root / "modules").mkdir()
        for index in range(136):
            name = "modules/source-%03d.nix" % index
            (self.root / name).write_bytes(self.content)
            self.value["files"].append(dict(self.value["files"][0], path=name))
        self.write_review()
        result = tool.pack(self.root, self.output)
        self.assertEqual(result["files"], 137)
        self.assertEqual(tool.verify(self.output, result["sha256"]), result)
        with tarfile.open(self.output) as archive:
            self.assertEqual(set(archive.getnames()), {"review.json", "SHA256SUMS"} |
                             {"source/" + item["path"] for item in self.value["files"]})
            self.assertEqual(len(archive.getmembers()), 139)

    def test_manifest_byte_limit_bounds_large_file_lists(self):
        self.value["files"].extend(dict(self.value["files"][0], path="f%d.nix" % i)
                                   for i in range(1024))
        self.write_review()
        raw = (self.root / "review.json").read_bytes()
        self.assertGreater(len(raw), tool.MAX_MANIFEST)
        self.assertLess(sum(item["bytes"] for item in self.value["files"]), tool.MAX_TOTAL)
        self.refuse_pack("FILE_SIZE_LIMIT")
        with self.assertRaisesRegex(tool.Refused, "MANIFEST_LIMIT"):
            tool.manifest(raw)

    def test_nonempty_file_list_total_size_and_individual_size_limits(self):
        cases = [([], "FILE_COUNT_LIMIT"),
                 ([dict(self.value["files"][0], bytes=tool.MAX_FILE + 1)], "FILE_SIZE_LIMIT"),
                 ([dict(self.value["files"][0], path="f%d.nix" % i, bytes=tool.MAX_FILE) for i in range(5)], "TOTAL_SIZE_LIMIT")]
        for files, code in cases:
            with self.subTest(code=code):
                self.value["files"] = files
                self.write_review()
                self.refuse_pack(code)

    def test_missing_entrypoint_and_path_collision(self):
        self.value["entrypoint"] = "missing.nix"
        self.write_review()
        self.refuse_pack("ENTRYPOINT_MISSING")
        self.value["entrypoint"] = "configuration.nix"
        self.value["files"].append(dict(self.value["files"][0], path="configuration.nix/child"))
        self.write_review()
        self.refuse_pack("PATH_COLLISION")

    def test_verify_checks_digest_before_archive(self):
        self.output.write_bytes(b"not an archive")
        with self.assertRaisesRegex(tool.Refused, "ARCHIVE_DIGEST_MISMATCH"):
            tool.verify(self.output, "0" * 64)

    def test_tampered_archive_link_duplicate_and_extra_member(self):
        tool.pack(self.root, self.output)
        original = self.output.read_bytes()
        for mutation in ("link", "duplicate", "extra", "contents"):
            with self.subTest(mutation=mutation):
                output = io.BytesIO()
                with tarfile.open(fileobj=io.BytesIO(original)) as source, tarfile.open(fileobj=output, mode="w", format=tarfile.USTAR_FORMAT) as dest:
                    for entry in source:
                        raw = source.extractfile(entry).read()
                        if entry.name == "source/configuration.nix":
                            if mutation == "link":
                                entry.type, entry.linkname, entry.size = tarfile.SYMTYPE, "/outside", 0
                                raw = b""
                            if mutation == "contents":
                                raw = b"X" * len(raw)
                        dest.addfile(entry, io.BytesIO(raw))
                        if mutation == "duplicate" and entry.name == "review.json":
                            dest.addfile(entry, io.BytesIO(raw))
                    if mutation == "extra":
                        dest.addfile(tarfile.TarInfo("source/extra.nix"), io.BytesIO(b""))
                self.output.write_bytes(output.getvalue())
                with self.assertRaises(tool.Refused):
                    tool.verify(self.output, hashlib.sha256(output.getvalue()).hexdigest())

    def test_trailing_data_and_modified_checksum_member_refused(self):
        tool.pack(self.root, self.output)
        original = self.output.read_bytes()
        self.output.write_bytes(original + b"synthetic appended data")
        with self.assertRaisesRegex(tool.Refused, "NONCANONICAL_ARCHIVE"):
            tool.verify(self.output, hashlib.sha256(self.output.read_bytes()).hexdigest())
        tampered = original.replace(b"  review.json", b"  review.jsoX", 1)
        self.output.write_bytes(tampered)
        with self.assertRaisesRegex(tool.Refused, "SUMS_MISMATCH"):
            tool.verify(self.output, hashlib.sha256(tampered).hexdigest())

    def test_cli_failure_never_echoes_source_path_or_contents(self):
        sentinel = self.base / "synthetic-private-path-sentinel"
        result = subprocess.run([sys.executable, "-I", "-S", str(SOURCE), "pack", str(sentinel), str(self.output)],
                                capture_output=True, check=False, timeout=5)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout), {"status": "refused", "code": "INVALID_LOCAL_INPUT"})
        self.assertEqual(result.stderr, b"")
        self.assertNotIn(b"sentinel", result.stdout)

    def test_cli_pack_then_verify_without_evaluating_source(self):
        # This remains source text; neither command may evaluate the Nix import.
        content = b'{ ... }: import /synthetic-source-that-must-never-be-read\n'
        (self.root / "configuration.nix").write_bytes(content)
        self.value["files"][0].update(bytes=len(content), sha256=hashlib.sha256(content).hexdigest())
        self.write_review()
        command = [sys.executable, "-I", "-S", str(SOURCE)]
        packed = subprocess.run(command + ["pack", str(self.root), str(self.output)],
                                capture_output=True, check=True, timeout=5)
        receipt = json.loads(packed.stdout)
        checked = subprocess.run(command + ["verify", str(self.output), receipt["sha256"]],
                                 capture_output=True, check=True, timeout=5)
        self.assertEqual(json.loads(checked.stdout), receipt)
        self.assertEqual(packed.stderr + checked.stderr, b"")
        self.assertEqual(receipt["status"], "integrity-checked")
        self.assertFalse(receipt["source_graph_verified_by_tool"])
        self.assertNotIn(b"synthetic-source", packed.stdout + checked.stdout)


if __name__ == "__main__":
    unittest.main()
