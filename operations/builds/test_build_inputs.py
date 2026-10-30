#!/usr/bin/env python3
"""Adversarial tests for the build input boundary, without real credentials."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import prepare
import verify_inputs


def archive(entries):
    result = io.BytesIO()
    with tarfile.open(fileobj=result, mode="w:gz") as target:
        for name, content, kind in entries:
            member = tarfile.TarInfo(name)
            member.type = kind
            if kind == tarfile.REGTYPE:
                member.size = len(content)
                target.addfile(member, io.BytesIO(content))
            else:
                member.linkname = content.decode()
                target.addfile(member)
    return result.getvalue()


def specification(data):
    return {"name": "fixture", "version": "1.0.0", "source": prepare.REGISTRY, "checksum": prepare.digest(data)}


class ArchiveBoundary(unittest.TestCase):
    def test_verified_archive_produces_deterministic_cargo_checksums(self):
        data = archive([("fixture-1.0.0/src/lib.rs", b"pub fn fixture() {}", tarfile.REGTYPE)])
        first = prepare.crate_files(data, specification(data))
        self.assertEqual(first, prepare.crate_files(data, specification(data)))
        checksums = json.loads(first[".cargo-checksum.json"])
        self.assertEqual(checksums["package"], prepare.digest(data))
        self.assertEqual(checksums["files"]["src/lib.rs"], prepare.digest(first["src/lib.rs"]))

    def test_archive_hash_mismatch_is_refused(self):
        data = archive([("fixture-1.0.0/Cargo.toml", b"fixture", tarfile.REGTYPE)])
        with self.assertRaisesRegex(prepare.Refused, "CRATE_CHECKSUM_MISMATCH"):
            prepare.crate_files(data + b"tampered", specification(data))

    def test_archive_cannot_escape_its_root(self):
        for name in ("fixture-1.0.0/../outside", "/fixture-1.0.0/src/lib.rs", "other/src/lib.rs", "fixture-1.0.0/a/../../outside"):
            with self.subTest(name=name), self.assertRaises(prepare.Refused):
                data = archive([(name, b"malicious", tarfile.REGTYPE)])
                prepare.crate_files(data, specification(data))

    def test_links_and_special_files_are_refused(self):
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE, tarfile.CHRTYPE):
            with self.subTest(kind=kind), self.assertRaises(prepare.Refused):
                data = archive([("fixture-1.0.0/src/lib.rs", b"/outside", kind)])
                prepare.crate_files(data, specification(data))

    def test_duplicate_member_and_injected_cargo_checksum_are_refused(self):
        for entries in (
            [("fixture-1.0.0/src/lib.rs", b"one", tarfile.REGTYPE), ("fixture-1.0.0/src/lib.rs", b"two", tarfile.REGTYPE)],
            [("fixture-1.0.0/.cargo-checksum.json", b"{}", tarfile.REGTYPE)],
        ):
            with self.subTest(entries=entries), self.assertRaises(prepare.Refused):
                data = archive(entries)
                prepare.crate_files(data, specification(data))


class SourceBoundary(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_source_mutation_is_refused(self):
        (self.root / "source.rs").write_bytes(b"changed")
        with self.assertRaisesRegex(prepare.Refused, "SOURCE_HASH_MISMATCH"):
            prepare.checked_bytes(self.root, "source.rs", prepare.digest(b"original"))

    def test_symlink_refused_even_when_bytes_match(self):
        (self.root / "original").write_bytes(b"identical")
        (self.root / "source.rs").symlink_to(self.root / "original")
        with self.assertRaisesRegex(prepare.Refused, "SOURCE_SYMLINK_REFUSED"):
            prepare.checked_bytes(self.root, "source.rs", prepare.digest(b"identical"))

    def test_symlink_ancestor_refused_for_sources_and_crate_cache(self):
        directory = self.root / "actual/cache"
        directory.mkdir(parents=True)
        data = b"identical"
        (directory / "fixture-1.0.0.crate").write_bytes(data)
        (self.root / "alias").symlink_to(self.root / "actual", target_is_directory=True)
        aliased = self.root / "alias/cache"
        with self.assertRaisesRegex(prepare.Refused, "SOURCE_SYMLINK_REFUSED"):
            prepare.checked_bytes(aliased, "fixture-1.0.0.crate", prepare.digest(data))
        with self.assertRaisesRegex(prepare.Refused, "SOURCE_SYMLINK_REFUSED"):
            prepare.crate_archive(aliased, {"name": "fixture", "version": "1.0.0", "checksum": prepare.digest(data)}, True)

    def test_fifo_is_refused_without_waiting_for_a_writer(self):
        os.mkfifo(self.root / "source.rs")
        program = "from pathlib import Path; import prepare; prepare.checked_bytes(Path(__import__('sys').argv[1]), 'source.rs', '0'*64)"
        completed = subprocess.run([sys.executable, "-c", program, str(self.root)], cwd=prepare.HERE, capture_output=True, timeout=2)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn(b"SOURCE_FILE_TYPE_REFUSED", completed.stderr)

    def test_sparse_oversized_file_is_refused_before_reading(self):
        with (self.root / "oversized").open("wb") as source:
            source.truncate(64 * 1024 * 1024 + 1)
        with self.assertRaisesRegex(prepare.Refused, "SOURCE_SIZE_LIMIT"):
            prepare.regular_bytes(self.root, "oversized")

    def test_git_commit_mismatch_refused_before_export(self):
        subprocess.run(["git", "init", "--quiet", str(self.root)], check=True)
        subprocess.run(["git", "-C", str(self.root), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "--quiet", "--allow-empty", "-m", "synthetic"], check=True)
        lock = {"sources": {"platform": {"commit": "0" * 40, "files": {}}}}
        with self.assertRaisesRegex(prepare.Refused, "SOURCE_COMMIT_MISMATCH"):
            prepare.verify_sources(self.root, lock)

    def test_missing_crate_does_not_fetch_without_explicit_flag(self):
        with patch("urllib.request.urlopen") as network:
            with self.assertRaisesRegex(prepare.Refused, "PINNED_CRATE_MISSING"):
                prepare.crate_archive(self.root, {"name": "fixture", "version": "1.0.0"}, False)
        network.assert_not_called()

    def test_wrong_cached_archive_is_never_replaced(self):
        target = self.root / "fixture-1.0.0.crate"
        target.write_bytes(b"wrong")
        with patch("urllib.request.urlopen") as network:
            with self.assertRaisesRegex(prepare.Refused, "CRATE_CHECKSUM_MISMATCH"):
                prepare.crate_archive(self.root, {"name": "fixture", "version": "1.0.0", "checksum": prepare.digest(b"right")}, True)
        network.assert_not_called()
        self.assertEqual(target.read_bytes(), b"wrong")

    def test_wrong_manifest_hash_is_refused_before_parsing(self):
        (self.root / "materialization.json").write_bytes(b"not json")
        with self.assertRaisesRegex(prepare.Refused, "SOURCE_HASH_MISMATCH"):
            verify_inputs.verify(self.root, "0" * 64)


class ArtifactBoundary(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.inputs, self.output = self.root / "inputs", self.root / "output"
        self.inputs.mkdir()
        self.output.mkdir()
        (self.inputs / "materialization.json").write_text(json.dumps({"source_commits": {"platform": "0" * 40}, "style_revision": "1" * 40}))

    def run_manifest(self):
        return subprocess.run([sys.executable, str(prepare.HERE / "artifact_manifest.py"), "--inputs", str(self.inputs), "--output", str(self.output), "--artifact", "rust-server"], capture_output=True, timeout=2)

    def test_output_fifo_refused_and_no_manifest_created(self):
        os.mkfifo(self.output / "not-a-payload")
        result = self.run_manifest()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"SOURCE_FILE_TYPE_REFUSED", result.stderr)
        self.assertFalse((self.output / "artifact.json").exists())

    def test_empty_output_symlink_refused_without_writing_target(self):
        actual = self.output
        self.output = self.root / "alias"
        self.output.symlink_to(actual, target_is_directory=True)
        result = self.run_manifest()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"SOURCE_SYMLINK_REFUSED", result.stderr)
        self.assertFalse((actual / "artifact.json").exists())

    def test_manifest_cannot_include_or_overwrite_a_previous_manifest(self):
        (self.output / "payload").write_bytes(b"synthetic payload")
        self.assertEqual(self.run_manifest().returncode, 0)
        first = (self.output / "artifact.json").read_bytes()
        self.assertEqual(set(json.loads(first)["payload_sha256"]), {"payload"})
        result = self.run_manifest()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"NEW_ARTIFACT_MANIFEST_REQUIRED", result.stderr)
        self.assertEqual((self.output / "artifact.json").read_bytes(), first)


if __name__ == "__main__":
    unittest.main()
