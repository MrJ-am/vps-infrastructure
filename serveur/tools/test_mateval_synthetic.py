#!/usr/bin/env python3
"""Exercise the actual fixture executable's refusal boundary without PostgreSQL.

Build the integration-postgres example first, then pass that exact executable.
Every child must fail before opening a database connection or an HTTP listener.
Only invented markers are used; child diagnostics are compared, never printed.
"""
import os
from pathlib import Path
import subprocess
import sys
import unittest


FIXTURE = "postgresql://mrjam_synthetic:mrjam_synthetic_only@127.0.0.1:55432/mrjam_synthetic"
MARKER = "SYNTHETIC_PRIVATE_MARKER"
BINARY = None


class FixtureExecutableGuards(unittest.TestCase):
    def refused(self, variables, code, arguments=()):
        # No inherited libpq options, generic database URL or credentials.
        environment = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL") if key in os.environ}
        environment.update(variables)
        result = subprocess.run(
            [str(BINARY), *arguments], env=environment,
            stdin=subprocess.DEVNULL, capture_output=True, timeout=5, check=False,
        )
        # Do not expose unexpected child output even when this test fails.
        self.assertTrue(result.returncode == 2, "fixture must exit with the closed refusal status")
        self.assertTrue(result.stdout == b"", "a refused fixture must not announce an HTTP port")
        expected = ('{"code":"' + code + '"}\n').encode()
        self.assertTrue(result.stderr == expected, "diagnostic must contain only the expected fixed code")

    def test_missing_fixture_never_falls_back_to_database_url(self):
        self.refused({"DATABASE_URL": MARKER}, "SYNTHETIC_DATABASE_REQUIRED")

    def test_nonliteral_urls_and_query_selectors_are_refused(self):
        for url in (
            FIXTURE.replace("127.0.0.1", "localhost"),
            FIXTURE.replace("55432", "5432"),
            FIXTURE.replace("/mrjam_synthetic", "/other_database"),
            FIXTURE + "?host=%2Fsynthetic-socket",
            FIXTURE + "?unknown=" + MARKER,
        ):
            with self.subTest(case="nonliteral fixture"):
                self.refused({"MRJAM_SYNTHETIC_DATABASE_URL": url}, "SYNTHETIC_DATABASE_REQUIRED")

    def test_libpq_environment_cannot_override_literal_fixture(self):
        for selector in ("PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD", "PGOPTIONS", "PGSSLMODE", "PGSSLROOTCERT"):
            with self.subTest(selector=selector):
                self.refused(
                    {"MRJAM_SYNTHETIC_DATABASE_URL": FIXTURE, selector: MARKER},
                    "SYNTHETIC_DATABASE_ENVIRONMENT_REFUSED",
                )

    def test_arguments_cannot_supply_a_target_or_sql_command(self):
        self.refused({"MRJAM_SYNTHETIC_DATABASE_URL": FIXTURE}, "INVALID_INVOCATION", (MARKER,))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: test_mateval_synthetic.py SYNTHETIC_EXECUTABLE")
    BINARY = Path(sys.argv.pop()).resolve(strict=True)
    unittest.main()
