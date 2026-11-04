"""Refuse other targets before any Docker invocation or database connection."""
import importlib.util
import subprocess
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("qualify", Path(__file__).with_name("qualify.py"))
candidate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(candidate)


class GuardTests(unittest.TestCase):
    def test_foreign_targets_and_arguments_refused_before_rehearsal(self):
        cases = [([], {}), (["--help"], {"MRJAM_SYNTHETIC_DATABASE_URL": candidate.URL})]
        for url in (candidate.URL + "?host=/tmp", candidate.URL.replace("127.0.0.1", "localhost"),
                    candidate.URL.replace("mrjam_synthetic", "production"), "invalid"):
            cases.append(([], {"MRJAM_SYNTHETIC_DATABASE_URL": url}))
        for args, environ in cases:
            with self.subTest(args=args, environ=environ), patch.object(candidate.sys, "argv", ["qualify.py", *args]), patch.dict(candidate.os.environ, environ, clear=True), patch.object(candidate, "rehearse") as run:
                self.assertEqual(candidate.main(), 1)
                run.assert_not_called()

    def test_pg_environment_refused(self):
        for name in ("PGHOST", "PGSERVICE", "PGOPTIONS", "PGPASSFILE"):
            with self.subTest(name=name), self.assertRaises(candidate.Refused):
                candidate.guard([], {"MRJAM_SYNTHETIC_DATABASE_URL": candidate.URL, name: "invented"})

    def test_hash_tampering_refused_before_container(self):
        with patch.object(candidate, "MIGRATIONS", {"001-collecte.sql": "0" * 64}), patch.object(candidate, "verify_container") as verify:
            with self.assertRaises(candidate.Refused):
                candidate.rehearse()
            verify.assert_not_called()

    def test_optimized_python_cannot_report_success_for_bad_restore(self):
        # Substitute only synthetic seams; exercise the complete scenario's
        # failure path under -O without opening Docker or any database.
        program = '''
import importlib.util, pathlib
from unittest.mock import patch
spec = importlib.util.spec_from_file_location("qualify", pathlib.Path("qualify.py"))
q = importlib.util.module_from_spec(spec)
spec.loader.exec_module(q)
def fake_sql(statement):
    if statement == "SHOW server_version_num;": return b"170011"
    if "pg_namespace" in statement: return b"0"
    return b"WRONG_SYNTHETIC_RESULT"
with patch.object(q, "sources", return_value={name:"" for name in q.MIGRATIONS}), patch.object(q,"verify_container"), patch.object(q,"sql",side_effect=fake_sql), patch.object(q,"pg",return_value=b"INVALID_ARCHIVE"):
    try: q.rehearse()
    except q.Refused: raise SystemExit(0)
    raise SystemExit(1)
'''
        result = subprocess.run([sys.executable, '-O', '-c', program], cwd=Path(__file__).parent,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
