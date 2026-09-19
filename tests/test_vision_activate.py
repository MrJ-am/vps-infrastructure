import importlib.util
from email.message import Message
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "vision_activate", ROOT / "scripts/vision-activate.py"
)
VISION_ACTIVATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VISION_ACTIVATE)


class CurrentLinkRollback(unittest.TestCase):
    def test_existing_link_is_detached_then_restored(self):
        with tempfile.TemporaryDirectory() as directory:
            current = Path(directory) / "current"
            current.symlink_to("releases/old")

            previous = VISION_ACTIVATE.detach_current_link(current)
            self.assertEqual(previous, "releases/old")
            self.assertFalse(current.is_symlink())

            current.symlink_to("releases/candidate")
            VISION_ACTIVATE.restore_current_link(current, previous)
            self.assertTrue(current.is_symlink())
            self.assertEqual(os.readlink(current), "releases/old")

    def test_candidate_link_is_removed_when_none_existed(self):
        with tempfile.TemporaryDirectory() as directory:
            current = Path(directory) / "current"

            previous = VISION_ACTIVATE.detach_current_link(current)
            self.assertIsNone(previous)
            current.symlink_to("releases/candidate")

            VISION_ACTIVATE.restore_current_link(current, previous)
            self.assertFalse(current.is_symlink())
            self.assertFalse(current.exists())

    def test_real_directory_is_never_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            current = Path(directory) / "current"
            current.mkdir()

            with self.assertRaisesRegex(RuntimeError, "sans être un lien"):
                VISION_ACTIVATE.detach_current_link(current)


class HttpsDiagnostics(unittest.TestCase):
    def test_authenticated_refusal_reports_status_and_public_error_only(self):
        headers = Message()
        headers["Content-Type"] = "application/json"
        headers["WWW-Authenticate"] = 'Basic realm="Vision"'
        responses = iter([
            (401, headers, b'{"error":"authentication_required"}'),
            (401, headers, b'{"error":"authentication_required"}'),
        ])

        with mock.patch.object(VISION_ACTIVATE, "request", side_effect=lambda *args, **kwargs: next(responses)):
            with self.assertRaisesRegex(
                RuntimeError,
                r"Santé authentifiée HTTP 401 \(authentication_required\)",
            ):
                VISION_ACTIVATE.verify_http("vision.example", "user", "secret")

    def test_empty_internal_error_still_reports_http_status(self):
        headers = Message()
        headers["Content-Type"] = "application/json"
        headers["WWW-Authenticate"] = 'Basic realm="Vision"'
        responses = iter([
            (401, headers, b'{"error":"authentication_required"}'),
            (500, headers, b""),
        ])

        with mock.patch.object(VISION_ACTIVATE, "request", side_effect=lambda *args, **kwargs: next(responses)):
            with self.assertRaisesRegex(
                RuntimeError,
                r"Santé authentifiée HTTP 500 \(réponse vide\)",
            ):
                VISION_ACTIVATE.verify_http("vision.example", "user", "secret")


if __name__ == "__main__":
    unittest.main()
