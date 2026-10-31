import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("delivery", ROOT / "verify_delivery.py")
delivery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(delivery)


class Delivery(unittest.TestCase):
    def test_pinned_manifest_is_readable(self):
        manifest = delivery.expected_manifest()
        self.assertEqual(manifest["closure_paths"], 83)
        self.assertEqual(len(manifest["closure"]), 83)

    def test_byte_mutation_and_truncation_refused(self):
        expected = {"bytes": 4, "sha256": hashlib.sha256(b"good").hexdigest()}
        with tempfile.TemporaryDirectory() as temporary:
            p = Path(temporary) / "artifact"
            for data in (b"good", b"evil", b"bad", b"goodextra"):
                p.write_bytes(data)
                if data == b"good":
                    delivery.verify_export(p, expected)
                else:
                    with self.subTest(data=data), self.assertRaises(ValueError):
                        delivery.verify_export(p, expected)

    def test_links_and_fifo_refused_without_reading(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "source").write_bytes(b"good")
            (root / "link").symlink_to(root / "source")
            os.mkfifo(root / "fifo")
            for name in ("link", "fifo"):
                with self.subTest(name=name), self.assertRaises((ValueError, OSError)):
                    delivery.read_bounded(root / name, 10)

    def test_closure_content_and_all_references_are_bound(self):
        expected = {"/nix/store/synthetic-a": {"nar_hash": "sha256-synthetic", "nar_size": 42,
                                              "references": ["/nix/store/synthetic-a"]}}
        info = {"/nix/store/synthetic-a": {"narHash": "sha256-synthetic", "narSize": 42,
                                          "references": ["/nix/store/synthetic-a"]}}
        delivery.verify_store(info, expected)
        cases = []
        for key, value in (("narHash", "sha256-changed"), ("narSize", 43),
                           ("references", []), ("references", ["/nix/store/extra"])):
            altered = copy.deepcopy(info)
            altered["/nix/store/synthetic-a"][key] = value
            cases.append(altered)
        cases.extend([{}, dict(info, extra=info["/nix/store/synthetic-a"])])
        for altered in cases:
            with self.subTest(altered=altered), self.assertRaises(ValueError):
                delivery.verify_store(altered, expected)

    def test_duplicate_paths_references_and_json_keys_refused(self):
        expected = {"/nix/store/a": {"nar_hash": "x", "nar_size": 1, "references": []}}
        entry = {"path": "/nix/store/a", "narHash": "x", "narSize": 1, "references": []}
        delivery.verify_store([entry], expected)
        with self.assertRaises(ValueError):
            delivery.verify_store([entry, entry], expected)
        with self.assertRaises(ValueError):
            json.loads('{"path":1,"path":2}', object_pairs_hook=delivery.unique)
        entry["references"] = ["/nix/store/a", "/nix/store/a"]
        with self.assertRaises(ValueError):
            delivery.verify_store([entry], expected)


if __name__ == "__main__":
    unittest.main()
