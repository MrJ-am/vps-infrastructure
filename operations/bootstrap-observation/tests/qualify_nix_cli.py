#!/usr/bin/env python3
"""Cloud-only Nix CLI qualification; never a production diagnostic or observer.

Run inside operations/tools/nix-local.sh --offline-container with the already
qualified observation closure. The corruption test owns a separate temporary
store and never modifies that closure or the normal Nix store.
"""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "/nix/store/25rzj9i3jv9f1878dwgkysnc454ndr84-mrjam-observe-adoption-v2"
FEATURE = ["--extra-experimental-features", "nix-command"]
VERIFY = ["store", "verify", "--offline", "--no-trust", "--recursive"]
INFO = ["path-info", "--offline", "--json", "--recursive"]
spec = importlib.util.spec_from_file_location("delivery", ROOT / "verify_delivery.py")
delivery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(delivery)


class NixCli(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get("MRJAM_SYNTHETIC_NIX_TEST") != "1":
            raise RuntimeError("CLOUD_SYNTHETIC_TEST_ONLY")
        cls.environment = dict(os.environ)
        # Override the Cloud wrapper's implicit feature activation. This is
        # per-process configuration, not an edit to any persistent nix.conf.
        cls.environment["NIX_CONFIG"] = "experimental-features =\nsandbox = false\n"
        cls.environment["LC_ALL"] = "C"
        cls.environment["TERM"] = "dumb"

    def run_command(self, argv):
        return subprocess.run(argv, env=self.environment, stdin=subprocess.DEVNULL,
                              capture_output=True, timeout=180, check=False)

    def test_01_pinned_nix_version(self):
        result = self.run_command(["nix", "--version"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), b"nix (Nix) 2.34.8")

    def test_02_original_verification_fails_when_feature_disabled(self):
        result = self.run_command(["nix", *VERIFY, PACKAGE])
        self.assertEqual(result.returncode, 1)
        self.assertIn(b"experimental Nix feature 'nix-command' is disabled", result.stderr)

    def test_03_original_metadata_command_also_requires_feature(self):
        result = self.run_command(["nix", *INFO, PACKAGE])
        self.assertEqual(result.returncode, 1)
        self.assertIn(b"experimental Nix feature 'nix-command' is disabled", result.stderr)

    def test_04_explicit_feature_verifies_exact_delivered_closure(self):
        result = self.run_command(["nix", *FEATURE, *VERIFY, PACKAGE])
        self.assertEqual(result.returncode, 0, result.stderr)
        metadata = self.run_command(["nix", *FEATURE, *INFO, PACKAGE])
        self.assertEqual(metadata.returncode, 0, metadata.stderr)
        info = json.loads(metadata.stdout, object_pairs_hook=delivery.unique)
        expected = delivery.expected_manifest()
        self.assertEqual(expected["closure_paths"], 83)
        delivery.verify_store(info, expected["closure"])

    def test_05_content_corruption_remains_a_failure(self):
        with tempfile.TemporaryDirectory(prefix="mrjam-nix-cli-synthetic-") as temporary:
            root = Path(temporary)
            source = root / "synthetic-content"
            source.write_bytes(b"SYNTHETIC ORIGINAL\n")
            store_root = root / "isolated-store"
            store = "local?root=" + str(store_root)
            added = self.run_command(["nix-store", "--store", store, "--add", str(source)])
            self.assertEqual(added.returncode, 0, added.stderr)
            path = added.stdout.decode("utf-8").strip()
            self.assertTrue(path.startswith("/nix/store/"))
            verify = ["nix", *FEATURE, "--store", store, *VERIFY, path]
            intact = self.run_command(verify)
            self.assertEqual(intact.returncode, 0, intact.stderr)
            content = store_root / path.lstrip("/")
            self.assertTrue(content.is_file())
            content.chmod(0o600)
            content.write_bytes(b"SYNTHETIC CORRUPTION\n")
            refused = self.run_command(verify)
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn(b"was modified!", refused.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
