"""Synthetic disclosure/refusal tests. No SSH, real identity or production path."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("preflight", Path(__file__).with_name("preflight.py"))
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)
NGINX = "/nix/store/" + "0" * 32 + "-nginx.conf"
NEXTCLOUD = "/nix/store/" + "1" * 32 + "-nextcloud-with-apps"


class PreflightBoundaryTests(unittest.TestCase):
    def test_metadata_does_not_open_contents(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, "invented-private-file")
            path.write_text("SYNTHETIC_PRIVATE_VALUE")
            with patch.object(preflight.os, "open", side_effect=AssertionError("no content read")):
                result = preflight.metadata(path)
            self.assertEqual(result["kind"], "file")
            self.assertNotIn("SYNTHETIC_PRIVATE_VALUE", json.dumps(result))

    def test_metadata_does_not_follow_links(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, "link")
            path.symlink_to("absent-synthetic-target")
            self.assertEqual(preflight.metadata(path)["kind"], "symlink")

    def test_regular_reader_refuses_oversize_link_fifo_and_non_utf8(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, "file")
            path.write_bytes(b"x" * 17)
            link = Path(folder, "link")
            link.symlink_to(path)
            fifo = Path(folder, "fifo")
            os.mkfifo(fifo)
            for candidate in (path, link, fifo):
                with self.subTest(candidate=candidate.name), self.assertRaises((OSError, ValueError)):
                    preflight.read_small_regular(candidate, 16)
            path.write_bytes(b"\xff")
            with self.assertRaises(ValueError):
                preflight.read_small_regular(path, 16)

    def test_regular_reader_accepts_public_version(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, "PG_VERSION")
            path.write_text("17\n")
            self.assertEqual(preflight.read_small_regular(path, 16), "17\n")

    def test_nginx_refuses_non_store_and_ambiguous_configuration(self):
        for command in ("nginx -c /etc/private", "nginx -c " + NGINX + " -c " + NGINX,
                        "nginx -c /nix/store/../private", "nginx -c " + NGINX + ".private"):
            with self.subTest(command=command), patch.object(preflight, "run", return_value=(0, command)), \
                    patch.object(preflight, "read_small_regular", side_effect=AssertionError("must not read")):
                self.assertEqual(preflight.nginx_public_metadata(), {"state": "unknown"})

    def test_nginx_exports_only_closed_public_fields(self):
        fixture = "server_name forge.mrj.am cloud.mrj.am private.invalid mrj.am.evil;\n"
        fixture += "root " + NEXTCLOUD + ";\nroot /var/lib/private;\n"
        fixture += "listen 127.0.0.1:3002;\nprivate_setting SYNTHETIC_PRIVATE_VALUE;\n"
        with patch.object(preflight, "run", return_value=(0, "nginx -c " + NGINX)), \
                patch.object(preflight, "read_small_regular", return_value=fixture):
            self.assertEqual(preflight.nginx_public_metadata(), {
                "state": "observed", "public_domains": ["cloud.mrj.am", "forge.mrj.am"],
                "nextcloud_webroots": [NEXTCLOUD], "identity_port_3002_declared": True})

    def test_nginx_refuses_unbounded_domain_list(self):
        fixture = "server_name " + " ".join(f"synthetic-{n}.mrj.am" for n in range(33)) + ";"
        with patch.object(preflight, "run", return_value=(0, "nginx -c " + NGINX)), \
                patch.object(preflight, "read_small_regular", return_value=fixture):
            self.assertEqual(preflight.nginx_public_metadata(), {"state": "unknown"})

    def test_observation_cannot_claim_failed_commands_are_absent(self):
        with patch.object(preflight.os.path, "realpath", return_value=preflight.PREVIOUS), \
                patch.object(preflight.pwd, "getpwnam", side_effect=KeyError), \
                patch.object(preflight, "run", return_value=None), \
                patch.object(preflight, "metadata", return_value={"state": "unknown"}), \
                patch.object(preflight, "read_small_regular", side_effect=OSError), \
                patch.object(preflight.shutil, "disk_usage") as disk:
            disk.return_value.free = 1234
            result = preflight.collect()
        self.assertTrue(all(value == {"state": "unknown"} for value in result["units"].values()))
        self.assertTrue(all(value is None for value in result["identity_unauthenticated_http_status"].values()))


if __name__ == "__main__":
    unittest.main()
