import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "vision_prepare", ROOT / "scripts/vision-prepare.py"
)
VISION_PREPARE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VISION_PREPARE)


class NginxCandidateChecks(unittest.TestCase):
    def test_missing_candidate_certificate_uses_existing_pair_only_in_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            existing = root / "existing"
            missing = root / "missing"
            existing.mkdir()
            existing_cert = existing / "fullchain.pem"
            existing_key = existing / "key.pem"
            existing_chain = existing / "chain.pem"
            existing_cert.write_text("certificate")
            existing_key.write_text("key")
            existing_chain.write_text("chain")
            original = root / "nginx.conf"
            candidate = root / "nginx-test.conf"
            original_content = (
                f"ssl_certificate {existing_cert};\n"
                f"ssl_certificate_key {existing_key};\n"
                f"ssl_trusted_certificate {existing_chain};\n"
                f"ssl_certificate {missing / 'fullchain.pem'};\n"
                f"ssl_certificate_key {missing / 'key.pem'};\n"
                f"ssl_trusted_certificate {missing / 'chain.pem'}; # OCSP\n"
            )
            original.write_text(original_content)

            result = VISION_PREPARE.nginx_config_for_test(original, candidate)

            self.assertEqual(result, candidate)
            self.assertEqual(original.read_text(), original_content)
            self.assertEqual(candidate.read_text().count(str(existing_cert)), 2)
            self.assertEqual(candidate.read_text().count(str(existing_key)), 2)
            self.assertEqual(candidate.read_text().count(str(existing_chain)), 2)
            self.assertIn("; # OCSP", candidate.read_text())
            self.assertEqual(os.stat(candidate).st_mode & 0o777, 0o600)

    def test_complete_configuration_is_tested_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cert = root / "fullchain.pem"
            key = root / "key.pem"
            chain = root / "chain.pem"
            cert.write_text("certificate")
            key.write_text("key")
            chain.write_text("chain")
            original = root / "nginx.conf"
            original.write_text(
                f"ssl_certificate {cert};\n"
                f"ssl_certificate_key {key};\n"
                f"ssl_trusted_certificate {chain};\n"
            )

            result = VISION_PREPARE.nginx_config_for_test(
                original, root / "nginx-test.conf"
            )

            self.assertEqual(result, original)
            self.assertFalse((root / "nginx-test.conf").exists())

    def test_missing_pair_without_existing_fallback_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "nginx.conf"
            original.write_text(
                f"ssl_certificate {root / 'missing-cert.pem'};\n"
                f"ssl_certificate_key {root / 'missing-key.pem'};\n"
            )

            with self.assertRaisesRegex(RuntimeError, "Aucune paire TLS existante"):
                VISION_PREPARE.nginx_config_for_test(
                    original, root / "nginx-test.conf"
                )


if __name__ == "__main__":
    unittest.main()
