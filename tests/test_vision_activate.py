import importlib.util
from email.message import Message
import json
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


class SystemProfileRegistration(unittest.TestCase):
    def test_candidate_is_registered_in_the_nixos_system_profile(self):
        with mock.patch.object(VISION_ACTIVATE, "run") as run:
            VISION_ACTIVATE.register_system("/nix/store/candidate-system")

        run.assert_called_once_with(
            "nix-env",
            "--profile",
            "/nix/var/nix/profiles/system",
            "--set",
            "/nix/store/candidate-system",
        )


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

    def test_complete_mcp_and_database_probe(self):
        unauthorized = Message()
        unauthorized["Content-Type"] = "application/json"
        unauthorized["WWW-Authenticate"] = 'Basic realm="Vision"'
        ok = Message()
        ok["Content-Type"] = "application/json"
        tool_names = [
            "search_memory_sheets",
            "list_due_memory_sheets",
            "get_memory_sheet",
            "save_memory_sheet",
            "record_review",
        ]
        responses = iter([
            (401, unauthorized, b'{"error":"authentication_required"}'),
            (200, ok, b'{"status":"ok","version":"1.1.0"}'),
            (200, ok, b'{"api":"vision","version":"1.1.0"}'),
            (200, ok, b'{"message":"World"}'),
            (401, unauthorized, b'{"error":"authentication_required"}'),
            (200, ok, json.dumps({
                "jsonrpc": "2.0",
                "id": "initialize",
                "result": {
                    "serverInfo": {"name": "vision", "version": "1.1.0"},
                },
            }).encode()),
            (200, ok, json.dumps({
                "jsonrpc": "2.0",
                "id": "tools-list",
                "result": {"tools": [{"name": name} for name in tool_names]},
            }).encode()),
            (200, ok, json.dumps({
                "jsonrpc": "2.0",
                "id": "database-search",
                "result": {"isError": False, "content": []},
            }).encode()),
        ])

        with mock.patch.object(
            VISION_ACTIVATE,
            "request",
            side_effect=lambda *args, **kwargs: next(responses),
        ):
            self.assertTrue(
                VISION_ACTIVATE.verify_http("vision.example", "user", "secret")
            )
        with self.assertRaises(StopIteration):
            next(responses)


if __name__ == "__main__":
    unittest.main()
