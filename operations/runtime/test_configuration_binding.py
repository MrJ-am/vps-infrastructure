import json
import os
from pathlib import Path
import tempfile
import unittest

from verify_configuration import credential_bindings, read_public, unique


class ConfigurationBinding(unittest.TestCase):
    def test_credentials_are_bound_to_the_selected_unit(self):
        config = {"mateval": {"database": {"password_file":
            "/run/credentials/mrjam-rust-blue.service/db-mateval"}}}
        self.assertEqual(credential_bindings(config, "blue"), ["db-mateval"])
        with self.assertRaises(ValueError):
            credential_bindings(config, "green")

    def test_another_role_or_source_path_is_not_a_credential_binding(self):
        for name in ("db-vision", "../db-mateval", "db-mateval/", "db-mateval//"):
            config = {"audition": {"password_file":
                "/run/credentials/mrjam-rust-blue.service/" + name}}
            with self.subTest(name=name), self.assertRaises(ValueError):
                credential_bindings(config, "blue")
        with self.assertRaises(ValueError):
            credential_bindings({"audition": {"password_file": "/run/secrets/audition"}}, "blue")

    def test_explicit_unix_peer_needs_no_password_binding(self):
        database = {"transport": "unix", "password_file": None}
        config = {"mateval": {"database": database, "administration_database": database},
                  "vision": {"database": database, "administration_database": database,
                             "deletion_journal": database}, "audition": database}
        self.assertEqual(credential_bindings(config, "blue"), [])
        # Rust validates the complete transport/configuration first. This layer
        # must also preserve the equivalent absent optional field.
        del database["password_file"]
        self.assertEqual(credential_bindings(config, "green"), [])

    def test_admission_approval_is_a_distinct_selected_unit_credential(self):
        config = {"vision": {"database": {"password_file": None},
                             "admission_approval_credential_file":
                             "/run/credentials/mrjam-rust-blue.service/admission-approval"}}
        self.assertEqual(credential_bindings(config, "blue"), ["admission-approval"])
        with self.assertRaises(ValueError):
            credential_bindings(config, "green")
        for path in ("/run/secrets/admission-approval",
                     "/run/credentials/mrjam-rust-blue.service/db-vision",
                     "/run/credentials/mrjam-rust-blue.service/../admission-approval"):
            config["vision"]["admission_approval_credential_file"] = path
            with self.subTest(path=path), self.assertRaises(ValueError):
                credential_bindings(config, "blue")

    def test_duplicate_json_binding_refused_at_any_depth(self):
        for raw in ('{"assets":[],"assets":[]}', '{"mateval":{"database":1,"database":2}}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                json.loads(raw, object_pairs_hook=unique)

    def test_public_file_links_and_parent_links_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "real").mkdir()
            (root / "real" / "public.json").write_bytes(b"{}")
            (root / "link").symlink_to(root / "real", target_is_directory=True)
            (root / "file").symlink_to(root / "real" / "public.json")
            self.assertEqual(read_public(root / "real" / "public.json", 2), b"{}")
            for path in (root / "link" / "public.json", root / "file"):
                with self.subTest(path=path), self.assertRaises(OSError):
                    read_public(path, 100)

    def test_oversized_and_nonregular_files_refused_without_blocking(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "oversized").write_bytes(b"123")
            os.mkfifo(root / "fifo")
            for path in (root / "oversized", root / "fifo"):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    read_public(path, 2)


if __name__ == "__main__":
    unittest.main()
