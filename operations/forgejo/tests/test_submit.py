import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest

spec = importlib.util.spec_from_file_location("submit", Path(__file__).parents[1] / "submit.py")
submit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(submit)


class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.proposal = "a" * 64
        self.rules = "b" * 40
        self.payloads = [b"synthetic executable", b"synthetic frontend", b'{"synthetic":true}']
        self.receipt = {"schema_version": 1, "decision": "passed", "proposal_sha256": self.proposal,
                        "rules_revision": self.rules, "authority": "local-controller-receipt",
                        "artifacts": [{"name": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
                                      for (name, _), raw in zip(submit.ARTIFACTS, self.payloads)]}

    def tearDown(self):
        self.temporary.cleanup()

    def wire(self, header=None, payloads=None, suffix=b""):
        return json.dumps(self.receipt if header is None else header).encode() + b"\n" + b"".join(self.payloads if payloads is None else payloads) + suffix

    def receive(self, raw):
        directory = self.root / self.proposal
        directory.mkdir(mode=0o700)
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        left, right = socket.socketpair()
        def sender():
            try:
                right.sendall(raw)
            except BrokenPipeError:
                pass
            finally:
                right.close()
        thread = threading.Thread(target=sender)
        thread.start()
        try:
            return submit.receive(left, fd, self.proposal, self.rules, deadline=time.monotonic() + 2)
        finally:
            left.close()
            thread.join(3)
            os.close(fd)

    def test_collects_exact_bytes_and_verifies_cache(self):
        self.assertEqual(self.receive(self.wire()), self.receipt)
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            self.assertEqual(submit.cached(fd, self.proposal, self.rules), self.receipt)
            for (name, _), raw in zip(submit.ARTIFACTS, self.payloads):
                self.assertEqual((self.root / self.proposal / name).read_bytes(), raw)
        finally:
            os.close(fd)

    def test_rejects_payload_hash_mismatch(self):
        with self.assertRaisesRegex(submit.Refused, "ARTIFACT_HASH_MISMATCH"):
            self.receive(self.wire(payloads=[b"X" * len(self.payloads[0]), *self.payloads[1:]]))

    def test_rejects_truncated_payload(self):
        with self.assertRaisesRegex(submit.Refused, "TRUNCATED_ARTIFACT"):
            self.receive(self.wire()[:-1])

    def test_rejects_extra_bytes(self):
        with self.assertRaisesRegex(submit.Refused, "EXTRA_ARTIFACT_DATA"):
            self.receive(self.wire(suffix=b"extra"))

    def test_rejects_swapped_identity(self):
        value = {**self.receipt, "rules_revision": "c" * 40}
        with self.assertRaisesRegex(submit.Refused, "IDENTITY_MISMATCH"):
            self.receive(self.wire(header=value))

    def test_rejects_arbitrary_output_name(self):
        self.receipt["artifacts"][0]["name"] = "../../target"
        with self.assertRaisesRegex(submit.Refused, "INVALID_ARTIFACTS"):
            self.receive(self.wire())

    def test_rejects_size_limit(self):
        self.receipt["artifacts"][0]["bytes"] = 64 * 1024 * 1024 + 1
        with self.assertRaisesRegex(submit.Refused, "INVALID_ARTIFACTS"):
            self.receive(self.wire())

    def test_rejects_forged_cache_file_bytes(self):
        self.receive(self.wire())
        file = self.root / self.proposal / "server"
        file.chmod(0o600)
        file.write_bytes(b"Y" * len(self.payloads[0]))
        file.chmod(0o400)
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            with self.assertRaisesRegex(submit.Refused, "ARTIFACT_HASH_MISMATCH"):
                submit.cached(fd, self.proposal, self.rules)
        finally:
            os.close(fd)

    def test_rejects_cache_symlink(self):
        self.receive(self.wire())
        file = self.root / self.proposal / "server"
        file.unlink()
        file.symlink_to("frontend.tar")
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            with self.assertRaises(OSError):
                submit.cached(fd, self.proposal, self.rules)
        finally:
            os.close(fd)


if __name__ == "__main__":
    unittest.main()
