"""Reject a wrong database before opening files or starting browser/server."""
import json
import os
from pathlib import Path
import subprocess
import unittest


class RunnerGuard(unittest.TestCase):
    def test_invalid_destinations_are_closed_and_do_not_echo_values(self):
        runner = Path(__file__).with_name("run.mjs")
        marker = "SYNTHETIC_SECRET_MUST_NOT_BE_EMITTED"
        for value in [None, f"postgresql://{marker}@example.invalid/private",
                      f"postgresql://mrjam_synthetic:mrjam_synthetic_only@127.0.0.1:55432/mrjam_synthetic?host={marker}"]:
            with self.subTest(present=value is not None):
                environment = dict(os.environ)
                environment.pop("MRJAM_SYNTHETIC_DATABASE_URL", None)
                if value is not None:
                    environment["MRJAM_SYNTHETIC_DATABASE_URL"] = value
                result = subprocess.run(["node", str(runner), "/missing/site", "/missing/binary",
                                         "/missing/tools", "/missing/proof"], env=environment,
                                        capture_output=True, text=True, timeout=5, check=False)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertEqual(json.loads(result.stderr), {"code": "SYNTHETIC_DATABASE_REQUIRED"})
                self.assertNotIn(marker, result.stderr)


if __name__ == "__main__":
    unittest.main()
