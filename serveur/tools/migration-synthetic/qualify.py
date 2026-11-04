#!/usr/bin/env python3
"""Local synthetic migration/restore rehearsal; no production executor.

No arguments, SQL, archive, path or target can be supplied. The only permitted
database is the explicitly opted-in disposable Cloud fixture. Every object read
or dumped belongs to the fresh schema created by this invocation.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

URL = "postgresql://mrjam_synthetic:mrjam_synthetic_only@127.0.0.1:55432/mrjam_synthetic"
CONTAINER = "mrjam-codex-synthetic-postgres"
IMAGE = "docker.io/pgvector/pgvector@sha256:ac08538c6f8b9904c33c8224c5e5706dbe760aca29db1d096972b4052c22a75d"
ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = {
    "001-collecte.sql": "ed168c35bcdf2f5576631158a30b93ec27dc8c3ba2ecc623c7181c5afca00b83",
    "002-sessions-administrateur.sql": "6cf8f26b734cc5b383275bd002db608b1576af9f01be58da4161fa5a0db504d1",
}


class Refused(Exception):
    pass


def require(condition):
    if not condition:
        raise Refused("SYNTHETIC_ASSERTION_FAILED")


def guard(argv, environ):
    if argv or environ.get("MRJAM_SYNTHETIC_DATABASE_URL") != URL:
        raise Refused("SYNTHETIC_OPT_IN_REQUIRED")
    if any(key.startswith("PG") for key in environ):
        raise Refused("PG_ENVIRONMENT_REFUSED")


def sources():
    result = {}
    for name, expected in MIGRATIONS.items():
        raw = (ROOT / "components/mateval/migrations" / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise Refused("MIGRATION_HASH_MISMATCH")
        result[name] = raw.decode("utf-8")
    return result


def docker(arguments, body=None, expected=0):
    env = dict(os.environ)
    for key in ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"):
        env.pop(key, None)
    try:
        result = subprocess.run(
            ["docker", "--host=unix:///var/run/docker.sock", *arguments],
            input=body, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env=env, timeout=45, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise Refused("LOCAL_SYNTHETIC_COMMAND_FAILED") from None
    if (expected == 0 and result.returncode != 0) or (expected != 0 and result.returncode == 0):
        raise Refused("LOCAL_SYNTHETIC_COMMAND_FAILED")
    if len(result.stdout) > 2 * 1024 * 1024:
        raise Refused("LOCAL_OUTPUT_LIMIT")
    return result.stdout


def verify_container():
    # Read only the locally owned fixture's non-secret execution metadata.
    expression = '{{json .Config.Image}} {{json (index .Config.Labels "org.mrjam.environment")}} {{json .HostConfig.ReadonlyRootfs}}'
    result = docker(["container", "inspect", "--format", expression, CONTAINER]).decode().strip()
    expected = json.dumps(IMAGE) + ' "codex-synthetic-v1" true'
    if result != expected:
        raise Refused("SYNTHETIC_CONTAINER_MISMATCH")
    format_metadata = '{"mounts":{{json .Mounts}},"tmpfs":{{json .HostConfig.Tmpfs}},"network":{{json .HostConfig.NetworkMode}},"ports":{{json .HostConfig.PortBindings}}}'
    metadata = json.loads(docker(["container", "inspect", "--format", format_metadata, CONTAINER]))
    expected_tmpfs = {
        "/tmp": "rw,nosuid,nodev,noexec,size=64m",
        "/var/lib/postgresql/data": "rw,nosuid,nodev,noexec,size=512m,uid=999,gid=999",
        "/var/run/postgresql": "rw,nosuid,nodev,noexec,size=16m,uid=999,gid=999",
    }
    if (metadata["tmpfs"] != expected_tmpfs
            or any(mount["Type"] != "tmpfs" or mount["Destination"] not in expected_tmpfs for mount in metadata["mounts"])
            or metadata["network"] != "mrjam-codex-synthetic-local"
            or metadata["ports"] != {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "55432"}]}):
        raise Refused("SYNTHETIC_CONTAINER_MISMATCH")
    # Match the existing reviewed helper: bridge with loopback publication.
    # Docker internal networks cannot supply that fixture's published endpoint.
    # This is explicitly NOT a claim of outbound network isolation.
    if docker(["network", "inspect", "--format", '{{json .Internal}}', "mrjam-codex-synthetic-local"]).strip() != b"false":
        raise Refused("SYNTHETIC_CONTAINER_MISMATCH")


def pg(tool, arguments, body=None, expected=0):
    return docker([
        "exec", "-i", "--env", "PGHOST=/var/run/postgresql", "--env", "PGPORT=5432",
        "--env", "PGUSER=mrjam_synthetic", "--env", "PGDATABASE=mrjam_synthetic",
        "--env", "PGSERVICEFILE=/dev/null", "--env", "PGPASSFILE=/dev/null",
        CONTAINER, tool, *arguments,
    ], body, expected)


def sql(statement):
    return pg("psql", ["-X", "--set=ON_ERROR_STOP=1", "--quiet", "--tuples-only", "--no-align"], statement.encode()).strip()


def rehearse():
    migrations = sources()
    verify_container()
    if sql("SHOW server_version_num;") != b"170011":
        raise Refused("POSTGRES_VERSION_MISMATCH")
    schema = "mrjam_restore_" + secrets.token_hex(16)
    prefix = f"SET search_path = {schema};\n"
    created = False
    started = time.monotonic()
    checks = {}
    try:
        sql(f"CREATE SCHEMA {schema};")
        created = True
        sql(prefix + migrations["001-collecte.sql"])
        sql(prefix + """
INSERT INTO administrators(username,password_hash) VALUES('invented-administrator','not-a-password-hash');
INSERT INTO administrator_sessions(token_hash,administrator_id,expires_at)
SELECT 'invented-token-before',id,'2030-01-01T00:00:00Z' FROM administrators;
INSERT INTO corpus(version,digest,bank,codebook) VALUES('synthetic-restore','invented-digest','{}','{}');
INSERT INTO participations(id,token_hash,bank_version,levels,seed,question_order,production_order)
VALUES('00000000-0000-4000-8000-000000000001','invented-token','synthetic-restore',ARRAY['invented'],0,ARRAY['Q1'],'{}');
INSERT INTO answers(participation_id,question_id,production_id,note,initial_note,x,y,z,evaluated_axes)
VALUES('00000000-0000-4000-8000-000000000001','Q1','P1',0,NULL,0,0,0,ARRAY[]::text[]);
INSERT INTO interaction_events(participation_id,sequence,event,occurred_at,elapsed_ms,payload)
VALUES('00000000-0000-4000-8000-000000000001',1,'invented-event','2024-02-29T12:00:00Z',100,'{"invented":true}');
""")
        old_projection = "SELECT jsonb_agg(jsonb_build_array(token_hash,administrator_id,expires_at) ORDER BY token_hash)::text FROM administrator_sessions;"
        before = sql(prefix + old_projection)
        sql(prefix + migrations["002-sessions-administrateur.sql"])
        sql(prefix + migrations["002-sessions-administrateur.sql"])
        require(sql(prefix + old_projection) == before)
        checks["additive_migration_replay_preserves_old_projection"] = True
        require(sql(prefix + "SELECT count(*) FROM administrator_sessions WHERE last_seen IS NOT NULL;") == b"1")
        sql(prefix + "INSERT INTO administrator_sessions(token_hash,administrator_id,expires_at) SELECT 'invented-old-writer',id,'2030-01-01T00:00:00Z' FROM administrators;")
        require(sql(prefix + "SELECT count(*) FROM administrator_sessions WHERE last_seen IS NOT NULL;") == b"2")
        checks["old_column_insert_works_after_migration"] = True
        require(sql(prefix + "SELECT note = 0 AND initial_note IS NULL FROM answers;") == b"t")
        checks["zero_null_preserved"] = True
        snapshot_query = """SELECT jsonb_build_object(
'administrators',(SELECT jsonb_agg(to_jsonb(t) ORDER BY id) FROM administrators t),
'sessions',(SELECT jsonb_agg(to_jsonb(t) ORDER BY token_hash) FROM administrator_sessions t),
'corpus',(SELECT jsonb_agg(to_jsonb(t) ORDER BY version) FROM corpus t),
'participations',(SELECT jsonb_agg(to_jsonb(t) ORDER BY id) FROM participations t),
'answers',(SELECT jsonb_agg(to_jsonb(t) ORDER BY production_id) FROM answers t),
'events',(SELECT jsonb_agg(to_jsonb(t) ORDER BY participation_id,sequence) FROM interaction_events t))::text;"""
        expected = sql(prefix + snapshot_query)
        archive = pg("pg_dump", ["--format=custom", "--no-owner", "--no-acl", "--schema=" + schema])
        require(archive.startswith(b"PGDMP"))
        checks["actual_pg_dump_synthetic_schema"] = True
        sql(prefix + "INSERT INTO administrator_sessions(token_hash,administrator_id,expires_at) SELECT 'invented-after-backup',id,'2030-01-01T00:00:00Z' FROM administrators;")
        require(sql(prefix + snapshot_query) != expected)
        sql(f"DROP SCHEMA {schema} CASCADE;")
        pg("pg_restore", ["--exit-on-error", "--single-transaction", "--no-owner", "--no-privileges", "--dbname=mrjam_synthetic"], b"invalid-synthetic-archive", expected=1)
        require(sql(f"SELECT count(*) FROM pg_namespace WHERE nspname='{schema}';") == b"0")
        checks["invalid_restore_refused_without_partial_schema"] = True
        pg("pg_restore", ["--exit-on-error", "--single-transaction", "--no-owner", "--no-privileges", "--dbname=mrjam_synthetic"], archive)
        require(sql(prefix + snapshot_query) == expected)
        checks["restore_matches_synthetic_snapshot"] = True
        require(sql(prefix + "SELECT count(*) FROM administrator_sessions WHERE token_hash='invented-after-backup';") == b"0")
        checks["post_backup_write_loss_demonstrated"] = True
        require(sql(prefix + "INSERT INTO administrators(username,password_hash) VALUES('invented-after-restore','not-a-hash') RETURNING id;") == b"2")
        checks["identity_sequence_restored"] = True
        return {
            "schema_version": 1, "scope": "synthetic-local-only", "status": "passed",
            "production_authorized": False, "postgres_version": "17.11",
            "migration_sha256": MIGRATIONS, "scenario_count": 1,
            "assertion_groups": checks, "elapsed_seconds": round(time.monotonic() - started, 3),
            "limits": ["SQL projection compatibility only, not an old binary rehearsal",
                       "One invented schema only, not all domains or production backups",
                       "An un-reconciled restore loses writes accepted after the snapshot",
                       "The existing fixture uses a bridge network, not outbound isolation",
                       "Local Docker fixture checks are not an authority or production ACL"],
        }
    finally:
        if created:
            sql(f"DROP SCHEMA IF EXISTS {schema} CASCADE;")
            if sql(f"SELECT count(*) FROM pg_namespace WHERE nspname='{schema}';") != b"0":
                raise Refused("SYNTHETIC_CLEANUP_FAILED")


def main():
    try:
        guard(sys.argv[1:], os.environ)
        result = rehearse()
        result["cleanup_verified"] = True
        print(json.dumps(result, sort_keys=True))
        return 0
    except Refused as error:
        print(json.dumps({"status": "refused", "code": str(error)}))
    except Exception:
        print('{"status":"failed","code":"SYNTHETIC_REHEARSAL_FAILED"}')
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
