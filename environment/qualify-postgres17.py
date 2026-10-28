#!/usr/bin/env python3
"""Run six existing Rust tests only against the literal disposable workshop.

The local PG17/pgvector service must already be running. No production database,
real migration, arbitrary SQL file or alternative database URL is accepted.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

import environment as helper

BASE = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sql(statement):
    if not helper.container_compatible(helper.CONTAINERS["postgres"]):
        raise helper.SetupError("SYNTHETIC_CONTAINER_COLLISION")
    return helper.require_docker([
        "exec", helper.CONTAINERS["postgres"], "psql", "--no-psqlrc",
        "--username=mrjam_synthetic", "--dbname=mrjam_synthetic",
        "--tuples-only", "--no-align", "--set=ON_ERROR_STOP=1", "--command=" + statement,
    ], "SYNTHETIC_QUALIFICATION_SQL_FAILED")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path,
                        help="Local Rust platform workspace containing the three existing test targets")
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    manifest = workspace / "Cargo.toml"
    if not manifest.is_file() or helper.LOCK["postgres"].get("major") != 17:
        raise helper.SetupError("PG17_QUALIFICATION_INPUT_INVALID")
    if not all(helper.service_status().values()):
        raise helper.SetupError("PG17_SYNTHETIC_SERVICES_NOT_READY")
    rust = helper.find_rust()
    if rust is None:
        raise helper.SetupError("RUST_PIN_MISMATCH")
    directory, process_env = rust
    process_env["PATH"] = str(directory) + ":" + process_env.get("PATH", "")
    # Do not inherit generic database selectors; keep platform proxies and trust.
    for name in ("DATABASE_URL", "PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD",
                 "PGSERVICE", "PGSERVICEFILE", "PGPASSFILE", "PGOPTIONS"):
        process_env.pop(name, None)
    process_env["VISION_TEST_ADMIN_URL"] = helper.DATABASE_URL
    process_env["MRJAM_SYNTHETIC_DATABASE_URL"] = helper.DATABASE_URL
    effective = json.loads(sql(
        "SELECT json_build_object('server_version',version(),"
        "'server_version_num',current_setting('server_version_num'),'database',current_database(),"
        "'current_user',current_user,'vector_version',(SELECT extversion FROM pg_extension WHERE extname='vector'),"
        "'vector_distance',('[1,2,3]'::vector <-> '[4,5,6]'::vector));"
    ))
    if effective["server_version_num"] != "170011" or effective["vector_version"] != "0.8.7":
        raise helper.SetupError("PG17_EFFECTIVE_VERSION_MISMATCH")
    if abs(effective["vector_distance"] - 27 ** 0.5) > 1e-12:
        raise helper.SetupError("PGVECTOR_SYNTHETIC_DISTANCE_FAILED")
    sources = ["Cargo.toml", "Cargo.lock", "crates/server/tests/mateval_http_postgres.rs",
               "components/vision/tests/postgres_synthetique.rs", "components/vision/tests/fixtures/postgres.sql",
               "components/mateval/tests/postgres.rs", "components/mateval/migrations/001-collecte.sql",
               "components/mateval/migrations/002-sessions-administrateur.sql"]
    before = {name: digest(workspace / name) for name in sources}
    results = []
    for package, feature, target, variable in (
        ("mrjam-vision", "integration-postgres", "postgres_synthetique", "VISION_TEST_ADMIN_URL"),
        ("mrjam-mateval", "integration-tests", "postgres", "MRJAM_SYNTHETIC_DATABASE_URL"),
        ("mrjam-server", "integration-postgres", "mateval_http_postgres", "MRJAM_SYNTHETIC_DATABASE_URL"),
    ):
        command = [str(directory / "cargo"), "test", "--locked", "--offline", "--manifest-path", str(manifest),
                   "--package", package, "--features", feature, "--test", target]
        code, output = helper.command(command, env=process_env, timeout=600, cwd=workspace)
        (helper.LOCAL / ("postgres17-" + package + ".log")).write_text(output)
        summary = re.findall(r"test result: [^\n]+", output)
        passed = code == 0 and any("ok. 2 passed; 0 failed; 0 ignored;" in line for line in summary)
        results.append({"package": package, "command": command, "database_variable": variable,
                        "database_target": "literal synthetic loopback URL only", "exit_code": code,
                        "summary": summary, "two_tests_passed": passed,
                        "output_sha256": hashlib.sha256(output.encode()).hexdigest()})
        print(json.dumps({"package": package, "exit_code": code, "two_tests_passed": passed}), flush=True)
    if before != {name: digest(workspace / name) for name in sources}:
        raise helper.SetupError("QUALIFIED_SOURCES_CHANGED")
    checks = []
    sql("CREATE SCHEMA environment_bootstrap_probe_pg17; "
        "CREATE TABLE environment_bootstrap_probe_pg17.marker(value integer PRIMARY KEY); "
        "INSERT INTO environment_bootstrap_probe_pg17.marker VALUES (17);")
    ids_before = {name: helper.require_docker(["container", "inspect", "--format", "{{.Id}}", container], "INSPECT_FAILED").strip()
                  for name, container in helper.CONTAINERS.items()}
    for command in (["bash", "setup.sh", "--install"], ["bash", "setup.sh", "--install"],
                    ["bash", "setup.sh", "--check"], ["bash", "services.sh", "up"],
                    ["bash", "services.sh", "up"], ["bash", "check.sh", "--services"]):
        code, output = helper.command(command, timeout=180)
        checks.append({"command": command, "exit_code": code,
                       "reports": [json.loads(line) for line in output.splitlines() if line.startswith("{")]})
    ids_after = {name: helper.require_docker(["container", "inspect", "--format", "{{.Id}}", container], "INSPECT_FAILED").strip()
                 for name, container in helper.CONTAINERS.items()}
    marker_ok = sql("SELECT value FROM environment_bootstrap_probe_pg17.marker;").strip() == "17"
    sql("DROP SCHEMA environment_bootstrap_probe_pg17 CASCADE;")
    mounts = json.loads(helper.require_docker(["container", "inspect", "--format", "{{json .Mounts}}",
                                               helper.CONTAINERS["postgres"]], "INSPECT_FAILED"))
    tmpfs = json.loads(helper.require_docker(["container", "inspect", "--format", "{{json .HostConfig.Tmpfs}}",
                                              helper.CONTAINERS["postgres"]], "INSPECT_FAILED"))
    no_persistent_mount = not any(mount.get("Type") in ("bind", "volume") for mount in mounts)
    passed = (all(item["two_tests_passed"] for item in results)
              and all(item["exit_code"] == 0 for item in checks)
              and ids_before == ids_after and marker_ok and no_persistent_mount)
    report = {"schema_version": 1, "observed_at_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "local disposable synthetic cluster; not production compatibility",
              "status": "passed" if passed else "failed", "postgres_pin": helper.LOCK["postgres"],
              "effective_database": effective, "tests": results, "test_count": 6,
              "setup_checks": checks, "idempotence": {"container_ids_unchanged": ids_before == ids_after,
                                                        "synthetic_row_preserved": marker_ok},
              "postgres_storage": {"no_bind_or_anonymous_volume": no_persistent_mount, "tmpfs": tmpfs},
              "source_sha256": before, "toolchain_lock_sha256": digest(BASE / "toolchains.lock.json"),
              "source_observations_snapshot": "postgres17-source-observations.json",
              "source_observations_sha256": digest(BASE / "postgres17-source-observations.json"),
              "baseline_postgres18": "evidence-postgres18/verification.json",
              "limitations": ["The source Nix module declares major17; actual production version was not queried",
                              "The vector distance smoke check does not qualify historical Vision vector-search business logic",
                              "The six tests use existing synthetic fixtures, not the full historical Vision migration",
                              "No production database or deployment was contacted"]}
    (BASE / "postgres17-qualification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "test_count": 6,
                      "server_version_num": effective["server_version_num"], "pgvector": effective["vector_version"]}))
    return 0 if passed else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (helper.SetupError, OSError, ValueError, KeyError):
        print('{"status":"error","code":"PG17_QUALIFICATION_FAILED"}')
        raise SystemExit(1) from None
