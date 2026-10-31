import hashlib
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("worker", ROOT / "worker.py")
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


def policy():
    return {"schema_version": 1, "rules_revision": "1" * 40, "validator_store": "/nix/store/" + "a" * 32 + "-rules", "bubblewrap_store": "/nix/store/" + "b" * 32 + "-bubblewrap", "closure_file": "/nix/store/" + "c" * 32 + "-closure/store-paths"}


class WorkerContract(unittest.TestCase):
    def fixture(self, files=None):
        parent = Path(tempfile.mkdtemp(prefix="mrjam-worker-unit-"))
        def cleanup():
            for base, _, _ in os.walk(parent, followlinks=False):
                Path(base).chmod(0o700)
            shutil.rmtree(parent)
        self.addCleanup(cleanup)
        files = files or {"source/main.rs": b"fn main() {}\n", "Cargo.lock": b"invented lock\n"}
        manifest = {"schema_version": 1, "rules_revision": "1" * 40, "files": [{"path": name, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()} for name, content in sorted(files.items())]}
        raw = json.dumps(manifest, sort_keys=True).encode()
        proposal = hashlib.sha256(raw).hexdigest()
        source = parent / proposal
        source.mkdir()
        for name, content in files.items():
            target = source / name
            target.parent.mkdir(exist_ok=True, parents=True)
            target.write_bytes(content)
            target.chmod(0o444)
        (source / "manifest.json").write_bytes(raw)
        (source / "manifest.json").chmod(0o444)
        for base, directories, _ in os.walk(source):
            Path(base).chmod(0o555)
        parent.chmod(0o555)
        return parent, source, proposal

    def check(self, root, proposal):
        return worker.verify_input(root, proposal, "1" * 40, owner=os.getuid())

    def test_closed_valid_source_manifest(self):
        root, source, proposal = self.fixture()
        self.assertEqual(self.check(root, proposal), source)

    def test_changed_equal_size_source_refused(self):
        root, source, proposal = self.fixture()
        target = source / "source/main.rs"
        target.chmod(0o644)
        target.write_bytes(b"fn evil() {}\n")
        target.chmod(0o444)
        with self.assertRaisesRegex(worker.Refused, "FILE_HASH_MISMATCH"):
            self.check(root, proposal)

    def test_input_not_root_owned_in_production_reader(self):
        root, source, proposal = self.fixture()
        if os.getuid() != 0:
            with self.assertRaisesRegex(worker.Refused, "UNTRUSTED_INPUT"):
                worker.verify_input(root, proposal, "1" * 40)

    def test_writable_source_refused(self):
        root, source, proposal = self.fixture()
        (source / "Cargo.lock").chmod(0o644)
        with self.assertRaisesRegex(worker.Refused, "UNTRUSTED_INPUT"):
            self.check(root, proposal)

    def test_symlink_fifo_hardlink_and_extra_file_refused(self):
        for kind in ("symlink", "fifo", "hardlink", "extra"):
            root, source, proposal = self.fixture()
            target = source / "Cargo.lock"
            source.chmod(0o755)
            if kind != "extra":
                target.unlink()
            if kind == "symlink":
                target.symlink_to("/etc/passwd")
            elif kind == "fifo":
                os.mkfifo(target, 0o444)
            elif kind == "hardlink":
                os.link(source / "source/main.rs", target)
            else:
                target = source / "undeclared"
                target.write_text("SYNTHETIC_ONLY")
                target.chmod(0o444)
            source.chmod(0o555)
            with self.subTest(kind=kind), self.assertRaises(worker.Refused):
                self.check(root, proposal)

    def test_wrong_manifest_rules_or_digest_refused(self):
        root, source, proposal = self.fixture()
        with self.assertRaises(worker.Refused):
            worker.verify_input(root, proposal, "2" * 40, owner=os.getuid())
        (source / "manifest.json").chmod(0o644)
        (source / "manifest.json").write_text("{}")
        (source / "manifest.json").chmod(0o444)
        with self.assertRaisesRegex(worker.Refused, "MANIFEST_MISMATCH"):
            self.check(root, proposal)

    def test_absolute_parent_duplicate_manifest_paths_refused(self):
        root, source, proposal = self.fixture()
        for path in ("/etc/passwd", "../source", "source/../main", "source//main"):
            manifest = {"schema_version": 1, "rules_revision": "1" * 40, "files": [{"path": path, "bytes": 0, "sha256": "0" * 64}]}
            raw = json.dumps(manifest).encode()
            other = hashlib.sha256(raw).hexdigest()
            root.chmod(0o755)
            folder = root / other
            folder.mkdir()
            (folder / "manifest.json").write_bytes(raw)
            (folder / "manifest.json").chmod(0o444)
            folder.chmod(0o555)
            root.chmod(0o555)
            with self.subTest(path=path), self.assertRaisesRegex(worker.Refused, "INVALID_PATH"):
                self.check(root, other)

    def test_closure_must_contain_validator_and_only_unique_store_roots(self):
        value = policy()
        valid = (value["validator_store"] + "\n").encode()
        self.assertEqual(worker.closure(valid, value["validator_store"]), [value["validator_store"]])
        for raw in (valid * 2, b"/etc/passwd\n", b"/nix/store/../../etc\n", b"", b"\xff"):
            with self.subTest(raw=raw), self.assertRaises(worker.Refused):
                worker.closure(raw, value["validator_store"])

    def test_candidate_cannot_supply_command_environment_or_mount(self):
        value = policy()
        for key, item in (("command", "sh"), ("validator_store", "/bin/sh"), ("closure_file", "/etc/passwd"), ("environment", {"TOKEN": "invented"})):
            bad = dict(value)
            bad[key] = item
            with self.subTest(key=key), self.assertRaises(worker.Refused):
                worker.policy(bad)

    def test_launch_is_immutable_and_has_no_host_network_or_data_bind(self):
        value = policy()
        source = worker.INPUT_ROOT / ("1" * 64)
        command = worker.command(value, [value["validator_store"]], source)
        for required in ("--unshare-all", "--unshare-user", "--clearenv", "--die-with-parent", "--new-session"):
            self.assertIn(required, command)
        self.assertEqual(command[-2:], [value["validator_store"] + "/bin/mrjam-validate", "/input"])
        self.assertNotIn("--share-net", command)
        self.assertNotIn("/var/run/docker.sock", command)
        self.assertNotIn("/run/credentials", command)

    def test_artifacts_are_bounded_hashed_and_sealed_outside_candidate(self):
        outputs = {name: os.memfd_create("synthetic-artifact", os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING) for name, _ in worker.ARTIFACTS}
        try:
            for fd in outputs.values():
                os.write(fd, b"invented compiled artifact")
            receipt = worker.seal_artifacts(outputs)
            self.assertEqual([item["name"] for item in receipt], [name for name, _ in worker.ARTIFACTS])
            for item in receipt:
                self.assertEqual(item["sha256"], hashlib.sha256(b"invented compiled artifact").hexdigest())
                with self.assertRaises(PermissionError):
                    os.write(outputs[item["name"]], b"mutation")
                with self.assertRaises(PermissionError):
                    os.ftruncate(outputs[item["name"]], 0)
        finally:
            for fd in outputs.values():
                os.close(fd)

    def test_seccomp_filter_is_sealed(self):
        fd = worker.seccomp_filter()
        try:
            self.assertEqual(fcntl.fcntl(fd, worker.F_GET_SEALS), worker.SEALS)
            with self.assertRaises(PermissionError):
                os.write(fd, b"altered filter")
        finally:
            os.close(fd)

    def test_cli_cannot_accept_commands_or_paths(self):
        process = subprocess.run([sys.executable, "-I", "-S", str(ROOT / "worker.py"), "SYNTHETIC_PRIVATE_MARKER"], capture_output=True, timeout=5)
        self.assertEqual(process.returncode, 2)
        self.assertNotIn(b"SYNTHETIC_PRIVATE_MARKER", process.stdout + process.stderr)
        self.assertEqual(process.stderr, b"")


if __name__ == "__main__":
    unittest.main()
