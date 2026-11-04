import io
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import subprocess
import tarfile
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import ci
import deploy


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.state = self.root / "state"
        self.state.mkdir()
        self.configuration = self.root / "nginx.conf"
        self.old = self.root / "old.conf"
        self.old.write_text("proxy_pass http://127.0.0.1:38101;")
        self.configuration.symlink_to(self.old)
        self.patches = [patch.object(deploy, "STATE", self.state),
                        patch.object(deploy, "NGINX_CONF", self.configuration)]
        for item in self.patches:
            item.start()
        self.addCleanup(lambda: [item.stop() for item in self.patches])
        self.addCleanup(self.temporary.cleanup)

    def test_recovery_restores_previous_route_and_records_failed_revision(self):
        candidate = self.root / "new.conf"
        candidate.write_text(deploy.switched(self.old.read_text(), "blue", "green"))
        deploy.symlink(candidate, self.configuration)
        deploy.atomic_json(self.state / "transaction.json", {
            "revision": "b" * 40, "old_configuration": str(self.old), "old_state": None})
        with patch.object(deploy, "reload_nginx") as reload:
            deploy.recover()
        self.assertEqual(self.configuration.resolve(), self.old)
        reload.assert_called_once()
        self.assertFalse((self.state / "transaction.json").exists())
        self.assertEqual(json.loads((self.state / "failed.json").read_text())["revision"], "b" * 40)

    def test_boot_recovery_restores_without_reloading_nginx(self):
        deploy.atomic_json(self.state / "transaction.json", {
            "revision": "b" * 40, "old_configuration": str(self.old), "old_state": None})
        with patch.object(deploy, "reload_nginx") as reload:
            deploy.restore()
        reload.assert_not_called()
        self.assertEqual(self.configuration.resolve(), self.old)

    def test_route_rewrite_preserves_unrelated_apps(self):
        original = self.old.read_text() + "\nproxy_pass http://127.0.0.1:3017;"
        new = deploy.switched(original, "blue", "green")
        self.assertEqual(deploy.active_slot(new), "green")
        self.assertIn("127.0.0.1:3017", new)
        self.assertEqual(self.configuration.resolve(), self.old)

    def test_ambiguous_routing_is_not_changed(self):
        with self.assertRaises(RuntimeError):
            deploy.active_slot("127.0.0.1:38101 127.0.0.1:38102")

    def test_pull_request_success_does_not_authorize_main_delivery(self):
        revision = "a" * 40
        branch = {"commit": {"id": revision}}
        runs = {"workflow_runs": [{"commit_sha": revision, "status": "success", "prettyref": "main",
                                   "trigger_event": "pull_request", "workflow_id": "ci.yml"}]}
        with patch.object(deploy, "api", side_effect=[json.dumps(branch), json.dumps(runs)]):
            self.assertIsNone(deploy.next_build())

    def test_failed_revision_is_not_retried_automatically(self):
        revision = "a" * 40
        deploy.atomic_json(self.state / "failed.json", {"revision": revision})
        with patch.object(deploy, "api", return_value=json.dumps({"commit": {"id": revision}})) as api:
            self.assertIsNone(deploy.next_build())
        self.assertEqual(api.call_count, 1)

    def test_source_archive_cannot_write_outside_checkout(self):
        raw = io.BytesIO()
        with tarfile.open(fileobj=raw, mode="w:gz") as archive:
            root = tarfile.TarInfo("root/")
            root.type = tarfile.DIRTYPE
            archive.addfile(root)
            entry = tarfile.TarInfo("root/../../escaped")
            entry.size = 1
            archive.addfile(entry, io.BytesIO(b"x"))
        with patch.object(ci, "api", return_value=raw.getvalue()):
            with self.assertRaises(tarfile.FilterError):
                ci.export("vision", "a" * 40, self.root / "checkout")
        self.assertFalse((self.root / "escaped").exists())

    def test_schema_change_is_detected_without_opening_a_database(self):
        migrations = self.root / "migrations"
        migrations.mkdir()
        sql = migrations / "001.sql"
        sql.write_text("CREATE TABLE invented (id integer);")
        before = ci.schema_digest(self.root)
        sql.write_text("CREATE TABLE invented (id integer, other text);")
        self.assertNotEqual(before, ci.schema_digest(self.root))

    @unittest.skipUnless(os.environ.get("NGINX_TEST_BINARY"), "Set NGINX_TEST_BINARY for the real routing test")
    def test_real_nginx_cutover_and_failure_rollback_keep_previous_backend(self):
        state = {"green_failed": False}

        def handler(slot):
            class Backend(BaseHTTPRequestHandler):
                def do_GET(self):
                    self.send_response(503 if slot == "green" and state["green_failed"] else 200)
                    self.end_headers()
                    self.wfile.write(slot.encode())

                def log_message(self, *_):
                    pass
            return Backend

        servers = {slot: ThreadingHTTPServer(("127.0.0.1", 0), handler(slot)) for slot in ["blue", "green"]}
        for server in servers.values():
            threading.Thread(target=server.serve_forever, daemon=True).start()
            self.addCleanup(server.server_close)
            self.addCleanup(server.shutdown)
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        ports = {slot: server.server_port for slot, server in servers.items()}
        self.old.write_text("pid " + str(self.root / "nginx.pid")
                            + "; error_log stderr crit; events {} http { access_log off; server { listen 127.0.0.1:"
                            + str(port) + "; location / { proxy_pass http://127.0.0.1:"
                            + str(ports["blue"]) + "; } } }")
        binary = os.environ["NGINX_TEST_BINARY"]
        arguments = [binary, "-p", str(self.root), "-c", str(self.configuration)]
        process = subprocess.Popen(arguments + ["-g", "daemon off;"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        def cleanup():
            process.terminate()
            process.wait(timeout=5)
        self.addCleanup(cleanup)

        def response():
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=0.5)
            try:
                connection.request("GET", "/")
                result = connection.getresponse()
                return result.status, result.read()
            finally:
                connection.close()

        def wait_for(slot):
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                try:
                    if response() == (200, slot.encode()):
                        return
                except OSError:
                    pass
                time.sleep(0.01)
            self.fail("Nginx did not serve " + slot)

        def reload():
            subprocess.run(arguments + ["-s", "reload"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)

        wait_for("blue")
        with patch.object(deploy, "PORTS", ports), patch.object(deploy, "reload_nginx", side_effect=reload):
            candidate = self.root / "candidate.conf"
            candidate.write_text(deploy.switched(self.old.read_text(), "blue", "green"))
            started = time.monotonic()
            deploy.symlink(candidate, self.configuration)
            reload()
            wait_for("green")
            cutover = time.monotonic() - started
            state["green_failed"] = True
            started = time.monotonic()
            failures = 0
            while failures < 2:
                failures = 0 if deploy.probe("green") else failures + 1
                if failures < 2:
                    time.sleep(1)
            deploy.rollback({"revision": "b" * 40, "old_configuration": str(self.old), "old_state": None})
            wait_for("blue")
            rollback = time.monotonic() - started
            self.assertTrue(deploy.probe("blue"))
        self.assertLess(cutover, 5)
        self.assertLess(rollback, 5)
        print(json.dumps({"synthetic_nginx_cutover_seconds": round(cutover, 3),
                          "failure_detection_and_rollback_seconds": round(rollback, 3)}))


if __name__ == "__main__":
    unittest.main()
