"""Real private temporary files and invented bytes; no Git histories or VPS.

Local uid/gid substitute OWNER=(0,0); production entrypoint ownership and
generation refusals are tested separately. No function implementation changes.
"""
import contextlib
import copy
import fcntl
import hashlib
import io
import os
from pathlib import Path
import signal
import tempfile
import types
import unittest
from unittest.mock import patch

import receive_source_bundles as m


PAYLOADS = tuple(("INVENTED-BUNDLE-%d\n" % i).encode() + bytes(range(i + 1)) for i in range(9))
PAYLOAD = b"".join(PAYLOADS)


def release():
    return {"schema_version": 1, "stream_bytes": len(PAYLOAD),
            "stream_sha256": hashlib.sha256(PAYLOAD).hexdigest(),
            "required_free_bytes": len(PAYLOAD) + m.GIB,
            "bundles": [{"name": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                        for name, data in zip(m.NAMES, PAYLOADS)]}


class NoRead:
    def read(self, _size):
        raise AssertionError("input must not be read")


class SmallChunks(io.BytesIO):
    def read(self, size):
        return super().read(min(size, 3))


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.fd = os.open(self.path, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, self.fd)
        owner = patch.object(m, "OWNER", (os.geteuid(), os.getegid()))
        owner.start()
        self.addCleanup(owner.stop)
        self.old_umask = os.umask(0o077)
        self.addCleanup(os.umask, self.old_umask)

    def receive(self, data=PAYLOAD, document=None):
        return m.receive(io.BytesIO(data), self.fd, document or release())

    def final(self, index=0):
        return self.path / (m.NAMES[index] + ".bundle")

    def put(self, index=0, data=None):
        path = self.final(index)
        path.write_bytes(PAYLOADS[index] if data is None else data)
        path.chmod(0o600)
        return path

    def assert_only(self, count):
        self.assertEqual(sorted(p.name for p in self.path.iterdir()),
                         sorted(n + ".bundle" for n in m.NAMES[:count]))

    def test_exact_stream_installs_nine_private_regular_files(self):
        self.assertEqual(self.receive(), 9)
        self.assert_only(9)
        for index, data in enumerate(PAYLOADS):
            meta = self.final(index).stat()
            self.assertEqual(self.final(index).read_bytes(), data)
            self.assertEqual(meta.st_mode & 0o777, 0o600)
            self.assertEqual((meta.st_uid, meta.st_gid), m.OWNER)
            self.assertEqual(meta.st_nlink, 1)

    def test_short_read_stream_has_identical_result(self):
        self.assertEqual(m.receive(SmallChunks(PAYLOAD), self.fd, release()), 9)
        self.assert_only(9)

    def test_repeat_preserves_existing_inodes_and_bytes(self):
        self.receive()
        before = [m.fingerprint(self.final(i).stat()) for i in range(9)]
        self.assertEqual(self.receive(), 0)
        self.assertEqual(before, [m.fingerprint(self.final(i).stat()) for i in range(9)])

    def test_partial_previous_completion_is_replayable(self):
        before = [m.fingerprint(self.put(i).stat()) for i in range(3)]
        self.assertEqual(self.receive(), 6)
        self.assertEqual(before, [m.fingerprint(self.final(i).stat()) for i in range(3)])
        self.assert_only(9)

    def test_corrupt_truncated_extended_and_wrong_overall_digest_accept_nothing(self):
        cases = [(PAYLOAD[:-1] + b"X", release()), (PAYLOAD[:-1], release()),
                 (PAYLOAD + b"X", release()), (b"", release())]
        wrong = release()
        wrong["stream_sha256"] = "0" * 64
        cases.append((PAYLOAD, wrong))
        for payload, document in cases:
            with self.subTest(size=len(payload), digest=document["stream_sha256"]), self.assertRaises(m.Refused):
                self.receive(payload, document)
            self.assert_only(0)

    def test_late_corruption_preserves_existing_verified_files(self):
        before = m.fingerprint(self.put().stat())
        with self.assertRaises(m.Refused):
            self.receive(PAYLOAD[:-1] + b"X")
        self.assertEqual(m.fingerprint(self.final().stat()), before)
        self.assert_only(1)

    def test_foreign_content_refused_before_reading(self):
        self.put(data=b"X" * len(PAYLOADS[0]))
        before = m.fingerprint(self.final().stat())
        with self.assertRaises(m.Refused):
            m.receive(NoRead(), self.fd, release())
        self.assertEqual(self.final().read_bytes(), b"X" * len(PAYLOADS[0]))
        self.assertEqual(m.fingerprint(self.final().stat()), before)

    def test_symlink_hardlink_public_mode_fifo_and_directory_refused_without_read(self):
        outside = self.path / "untouched"
        outside.write_bytes(PAYLOADS[0])
        outside.chmod(0o600)
        for kind in ("symlink", "hardlink", "public", "fifo", "directory"):
            with self.subTest(kind=kind):
                if kind == "symlink":
                    self.final().symlink_to(outside)
                elif kind == "hardlink":
                    os.link(outside, self.final())
                elif kind == "public":
                    self.put().chmod(0o644)
                elif kind == "fifo":
                    os.mkfifo(self.final(), 0o600)
                else:
                    self.final().mkdir(mode=0o700)
                with self.assertRaises((m.Refused, OSError)):
                    m.receive(NoRead(), self.fd, release())
                self.assertEqual(outside.read_bytes(), PAYLOADS[0])
                if kind == "directory":
                    self.final().rmdir()
                else:
                    self.final().unlink()

    def test_foreign_owner_or_group_metadata_refused(self):
        self.put()
        for owner in ((os.geteuid() + 1, os.getegid()), (os.geteuid(), os.getegid() + 1)):
            with self.subTest(owner=owner), patch.object(m, "OWNER", owner), self.assertRaises(m.Refused):
                m.receive(NoRead(), self.fd, release())

    def test_destination_created_during_input_refused_before_any_acceptance(self):
        outer = self
        class Concurrent(io.BytesIO):
            def read(self, size):
                result = super().read(size)
                if result == b"":
                    outer.put(8, b"FOREIGN")
                return result
        with self.assertRaises(m.Refused):
            m.receive(Concurrent(PAYLOAD), self.fd, release())
        self.assertEqual([p.name for p in self.path.iterdir()], [m.NAMES[8] + ".bundle"])
        self.assertEqual(self.final(8).read_bytes(), b"FOREIGN")

    def test_interrupt_during_input_cleans_staging_and_accepts_nothing(self):
        class Interrupted(io.BytesIO):
            def read(self, size):
                if self.tell() > 0:
                    m.interrupted(signal.SIGTERM, None)
                return super().read(size)
        with self.assertRaises(m.Refused):
            m.receive(Interrupted(PAYLOAD), self.fd, release())
        self.assert_only(0)

    def test_failure_between_installations_leaves_verified_subset_and_can_resume(self):
        original = os.link
        calls = 0
        def interrupted_link(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 4:
                raise OSError("INVENTED DISK FAILURE")
            return original(*args, **kwargs)
        with patch.object(m.os, "link", side_effect=interrupted_link), self.assertRaises(OSError):
            self.receive()
        self.assert_only(3)
        for i in range(3):
            self.assertEqual(self.final(i).stat().st_nlink, 1)
        self.assertEqual(self.receive(), 6)
        self.assert_only(9)

    def test_foreign_destination_race_is_never_overwritten(self):
        original = os.link
        def raced_link(*args, **kwargs):
            self.put(data=b"PRESERVE")
            return original(*args, **kwargs)
        with patch.object(m.os, "link", side_effect=raced_link), self.assertRaises(FileExistsError):
            self.receive()
        self.assertEqual(self.final().read_bytes(), b"PRESERVE")
        self.assert_only(1)

    def test_release_is_exactly_nine_ordered_fixed_names_and_bounded_bytes(self):
        self.assertEqual(m.validate_release(release()), release())
        cases = [None, {}, {**release(), "extra": True}]
        for field, value in (("schema_version", True), ("stream_bytes", True), ("stream_bytes", -1),
                             ("stream_sha256", "Z" * 64), ("required_free_bytes", len(PAYLOAD))):
            altered = release()
            altered[field] = value
            cases.append(altered)
        for field, value in (("name", "../other"), ("bytes", True), ("bytes", 0),
                             ("bytes", 65 * m.GIB), ("sha256", "a" * 63)):
            altered = release()
            altered["bundles"][0][field] = value
            cases.append(altered)
        altered = release()
        altered["bundles"].reverse()
        cases.append(altered)
        altered = release()
        altered["bundles"][-1] = copy.deepcopy(altered["bundles"][0])
        cases.append(altered)
        altered = release()
        altered["bundles"].pop()
        cases.append(altered)
        for document in cases:
            with self.subTest(document=document), self.assertRaises(m.Refused):
                m.validate_release(document)

    def test_unsealed_or_wrong_generation_or_identity_refuses_before_filesystem(self):
        with patch.object(m, "protected_directory") as opened:
            with self.assertRaises(m.Refused):
                m.deliver(None, NoRead())
            with patch.object(m, "PREVIOUS", "/wrong-generation"), self.assertRaises(m.Refused):
                m.deliver(release(), NoRead())
            for identity in ((os.geteuid() + 1, os.getegid()), (os.geteuid(), os.getegid() + 1)):
                with patch.object(m, "OWNER", identity), self.assertRaises(m.Refused):
                    m.deliver(release(), NoRead())
            opened.assert_not_called()

    def deliver_patches(self):
        stack = contextlib.ExitStack()
        stack.enter_context(patch.object(m, "PREVIOUS", os.path.realpath("/run/current-system")))
        stack.enter_context(patch.object(m, "protected_directory", side_effect=lambda _path: os.open(
            self.path, os.O_RDONLY | os.O_DIRECTORY)))
        return stack

    def test_concurrent_lock_refuses_before_input_and_preserves_existing(self):
        self.put()
        fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with self.deliver_patches(), self.assertRaises(BlockingIOError):
            m.deliver(release(), NoRead())
        self.assert_only(1)

    def test_insufficient_reserve_refuses_before_reading(self):
        unavailable = types.SimpleNamespace(f_bavail=0, f_frsize=4096)
        with self.deliver_patches(), patch.object(m.os, "fstatvfs", return_value=unavailable), \
                self.assertRaises(m.Refused):
            m.deliver(release(), NoRead())
        self.assert_only(0)

    def test_success_receipt_has_only_closed_metadata_and_no_activation(self):
        with self.deliver_patches():
            result = m.deliver(release(), io.BytesIO(PAYLOAD))
        self.assertEqual(result, {"schema_version": 1, "code": "SOURCE_BUNDLES_RECEIVED", "bundle_count": 9,
                                 "created_count": 9, "already_present_count": 0,
                                 "stream_sha256": hashlib.sha256(PAYLOAD).hexdigest(),
                                 "forgejo_imported": False, "application_activation": False})

    def test_main_unsealed_and_extra_argument_outputs_no_exception_or_input(self):
        for args in (["receiver"], ["receiver", "arbitrary-command"]):
            output = io.StringIO()
            handlers = {sig: signal.getsignal(sig) for sig in (signal.SIGALRM, signal.SIGTERM, signal.SIGINT)}
            try:
                with patch.object(m.sys, "argv", args), patch.object(m.sys, "stdin", types.SimpleNamespace(buffer=NoRead())), \
                        contextlib.redirect_stdout(output):
                    self.assertEqual(m.main(), 1)
            finally:
                for sig, handler in handlers.items():
                    signal.signal(sig, handler)
            self.assertEqual(output.getvalue(), '{"code":"SOURCE_BUNDLES_REFUSED","schema_version":1}\n')
        self.assert_only(0)


class DirectoryTests(unittest.TestCase):
    def setUp(self):
        local = Path(__file__).resolve().parents[2] / ".local"
        self.temp = tempfile.TemporaryDirectory(prefix="source-receiver-test-", dir=local)
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        owner = patch.object(m, "OWNER", (os.geteuid(), os.getegid()))
        owner.start()
        self.addCleanup(owner.stop)
        self.old_umask = os.umask(0o077)
        self.addCleanup(os.umask, self.old_umask)

    def test_complete_deliver_uses_actual_directory_walk_and_lock(self):
        destination = self.path / "private"
        with patch.object(m, "DIRECTORY", destination), \
                patch.object(m, "PREVIOUS", os.path.realpath("/run/current-system")):
            result = m.deliver(release(), io.BytesIO(PAYLOAD))
        self.assertEqual(result["created_count"], 9)
        self.assertEqual(destination.stat().st_mode & 0o777, 0o700)
        self.assertEqual(len(list(destination.iterdir())), 9)

    def test_public_directory_is_refused_without_changing_permissions(self):
        self.path.chmod(0o755)
        with self.assertRaises(m.Refused):
            m.protected_directory(self.path)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o755)

    def test_writable_ancestor_refused_before_creating_leaf(self):
        self.path.chmod(0o777)
        destination = self.path / "private"
        with self.assertRaises(m.Refused):
            m.protected_directory(destination)
        self.assertFalse(destination.exists())

    def test_symlink_ancestor_or_final_directory_never_followed(self):
        target = self.path / "untouched"
        target.mkdir(mode=0o700)
        link = self.path / "link"
        link.symlink_to(target, target_is_directory=True)
        for destination in (link, link / "private"):
            with self.subTest(destination=destination), self.assertRaises(OSError):
                m.protected_directory(destination)
        self.assertEqual(list(target.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
