#!/usr/bin/env python3
"""Disposable databases and certificates for the real CLI browser fixture.

There is intentionally no URL, SQL, role, container or migration argument. Only
the literal local synthetic container and the reviewed source trees are used.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import subprocess
import sys

URL = "postgresql://mrjam_synthetic:mrjam_synthetic_only@127.0.0.1:55432/mrjam_synthetic"
CONTAINER = "mrjam-codex-synthetic-postgres"
IMAGE = "docker.io/pgvector/pgvector@sha256:ac08538c6f8b9904c33c8224c5e5706dbe760aca29db1d096972b4052c22a75d"
LABEL = "e3f226ee76a0720fc53a173985be05709bb2e7c2e19ec5e8a2eb3c1b34795db2"
PLATFORM = Path(__file__).resolve().parents[2]
PASSWORD = "synthetic-runtime-browser-only"
OWNER = "synthetic.browser"
VISION_ROLES = ("vision_migration", "vision_administration", "vision_identite",
                "vision_cycle", "vision_admission", "vision_fermeture", "vision")


class Refused(Exception):
    pass


def guard() -> None:
    if os.environ.get("MRJAM_SYNTHETIC_DATABASE_URL") != URL:
        raise Refused("SYNTHETIC_DATABASE_REQUIRED")
    if any(name.startswith("PG") for name in os.environ):
        raise Refused("AMBIENT_DATABASE_CONFIGURATION_REFUSED")


def run(args: list[str], stdin: bytes | None = None) -> bytes:
    environment = {k: v for k, v in os.environ.items()
                   if not k.startswith("DOCKER_") and k != "CONTAINER_HOST"}
    result = subprocess.run(args, input=stdin, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=90, env=environment)
    if result.returncode:
        # Never print SQL, generated credentials or an arbitrary tool diagnostic.
        raise Refused("FIXTURE_COMMAND_FAILED")
    return result.stdout


def docker(*args: str, stdin: bytes | None = None) -> bytes:
    return run(["docker", "--host", "unix:///var/run/docker.sock", *args], stdin)


def verify_container() -> None:
    value = json.loads(docker("inspect", CONTAINER))
    if len(value) != 1:
        raise Refused("SYNTHETIC_CONTAINER_REFUSED")
    info = value[0]
    labels = info["Config"]["Labels"]
    if (info["Config"]["Image"] != IMAGE or not info["State"]["Running"]
            or labels.get("org.mrjam.environment") != "codex-synthetic-v1"
            or labels.get("org.mrjam.config") != LABEL
            or info["NetworkSettings"]["Ports"].get("5432/tcp")
            != [{"HostIp": "127.0.0.1", "HostPort": "55432"}]):
        raise Refused("SYNTHETIC_CONTAINER_REFUSED")


def sql(database: str, statement: str) -> str:
    if not re.fullmatch(r"(?:mrjam_synthetic|rb_[a-f0-9]{16}_(?:mateval|vision))", database):
        raise Refused("DATABASE_NAME_REFUSED")
    return docker("exec", "-i", CONTAINER, "psql", "-X", "-qAt", "-U",
                  "mrjam_synthetic", "-d", database, "-v", "ON_ERROR_STOP=1",
                  stdin=statement.encode()).decode().strip()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def workdir(argument: str) -> tuple[Path, str]:
    root = Path(argument)
    if (not root.is_absolute() or root.is_symlink() or root.resolve() != root
            or not re.fullmatch(r"mrjam-runtime-browser-[a-f0-9]{16}", root.name)
            or not root.is_dir() or root.stat().st_uid != os.getuid()
            or stat.S_IMODE(root.stat().st_mode) != 0o700):
        raise Refused("FIXTURE_DIRECTORY_REFUSED")
    return root, "rb_" + root.name.rsplit("-", 1)[1]


def private(path: Path, contents: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(contents)


def save(root: Path, state: dict) -> None:
    temporary = root / "fixture.next.json"
    private(temporary, (json.dumps(state, sort_keys=True, indent=2) + "\n").encode())
    temporary.replace(root / "fixture.json")


def role_names(prefix: str) -> dict[str, str]:
    if not re.fullmatch(r"rb_[a-f0-9]{16}", prefix):
        raise Refused("ROLE_PREFIX_REFUSED")
    # Vision migrations themselves bind SECURITY DEFINER/RLS to these exact
    # principals. Renaming only roles.sql would invalidate those policies.
    # Preexisting roles are refused before any mutation, and cleanup checks
    # every creation marker. Do not run beside another Vision SQL fixture.
    return {**{name: prefix + "_" + name for name in ("collecte", "science", "audition")},
            **{name: name for name in VISION_ROLES}}


def source(state: dict, relative: str) -> str:
    location = PLATFORM / relative
    if location.is_symlink() or not location.is_file():
        raise Refused("MIGRATION_SOURCE_REFUSED")
    content = location.read_bytes()
    state["migration_sources_sha256"][relative] = sha(content)
    return content.decode()


def setup(root: Path, prefix: str, bank_path: Path) -> dict:
    if (root / "fixture.json").exists():
        raise Refused("FIXTURE_ALREADY_EXISTS")
    marker = "mrjam-runtime-browser:" + prefix
    roles = role_names(prefix)
    databases = {name: prefix + "_" + name for name in ("mateval", "vision")}
    names = list(roles.values()) + list(databases.values())
    literals = ",".join("'" + name + "'" for name in names)
    existing = sql("mrjam_synthetic", f"SELECT rolname FROM pg_roles WHERE rolname IN ({literals}) UNION ALL SELECT datname FROM pg_database WHERE datname IN ({literals});")
    if existing:
        raise Refused("PREEXISTING_OBJECT_REFUSED")
    state = {"schema_version": 1, "marker": marker, "prefix": prefix,
             "roles": roles, "databases": databases, "created_roles": [],
             "created_databases": [], "migration_sources_sha256": {},
             "status": "creating", "production_access": False}
    save(root, state)
    for name in roles.values():
        sql("mrjam_synthetic", f"BEGIN; CREATE ROLE {name} LOGIN PASSWORD '{PASSWORD}' NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS; COMMENT ON ROLE {name} IS '{marker}'; COMMIT;")
        state["created_roles"].append(name)
        save(root, state)
    for name in databases.values():
        sql("mrjam_synthetic", f"CREATE DATABASE {name} TEMPLATE template0;")
        # Track immediately; cleanup refuses a missing or mismatched marker.
        state["created_databases"].append(name)
        save(root, state)
        sql("mrjam_synthetic", f"COMMENT ON DATABASE {name} IS '{marker}';")
    mateval = databases["mateval"]
    sql(mateval, "REVOKE CREATE ON SCHEMA public FROM PUBLIC; CREATE SCHEMA mateval; REVOKE ALL ON SCHEMA mateval FROM PUBLIC;")
    for name in ("001-collecte.sql", "002-sessions-administrateur.sql"):
        sql(mateval, "SET search_path=mateval;\n" + source(state, "components/mateval/migrations/" + name))
    collector, science = roles["collecte"], roles["science"]
    sql(mateval, f"""
      GRANT USAGE ON SCHEMA mateval TO {collector},{science};
      GRANT SELECT ON mateval.corpus TO {collector};
      GRANT SELECT,INSERT,UPDATE ON mateval.participations TO {collector};
      GRANT SELECT,INSERT,DELETE ON mateval.answers TO {collector};
      GRANT SELECT,INSERT ON mateval.interaction_events TO {collector};
      GRANT SELECT ON ALL TABLES IN SCHEMA mateval TO {science};
      GRANT INSERT,UPDATE(id) ON mateval.administrators TO {science};
      GRANT INSERT,UPDATE,DELETE ON mateval.administrator_sessions TO {science};
      GRANT USAGE ON SEQUENCE mateval.administrators_id_seq TO {science};
    """)
    # Public authored questionnaire, already allowed and artifact-verified by the
    # caller. The codebook, participants and every answer are invented here.
    bank = bank_path.read_bytes()
    value = json.loads(bank)
    if len(bank) > 5 * 1024 * 1024 or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", value["version"]):
        raise Refused("PUBLIC_BANK_REFUSED")
    encoded = base64.b64encode(bank).decode()
    digest = run(["node", "--input-type=module", "-e",
                  "import{createHash}from'node:crypto';let s='';for await(const c of process.stdin)s+=c;process.stdout.write(createHash('sha256').update(JSON.stringify({bank:JSON.parse(s),codebook:{synthetic:true}})).digest('hex'));"], bank).decode()
    if not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise Refused("CORPUS_DIGEST_REFUSED")
    sql(mateval, f"INSERT INTO mateval.corpus(version,digest,bank,codebook) VALUES ('{value['version']}','{digest}',convert_from(decode('{encoded}','base64'),'UTF8')::jsonb,'{{\"synthetic\":true}}');")
    state["public_bank_sha256"] = sha(bank)
    state["synthetic_corpus_digest"] = digest
    state["corpus_digest_scope"] = "JSON.stringify bank plus invented codebook; no production corpus claim"
    vision = databases["vision"]
    sql(vision, "CREATE EXTENSION vector;")
    migrations = sorted((PLATFORM / "components/vision/migrations").glob("[0-9][0-9][0-9]_*.sql"))
    if [int(path.name[:3]) for path in migrations] != list(range(1, 28)):
        raise Refused("VISION_MIGRATION_SET_REFUSED")
    for migration in migrations:
        sql(vision, source(state, str(migration.relative_to(PLATFORM))))
    original = source(state, "components/vision/scripts/roles.sql")
    state["vision_roles_sha256"] = sha(original.encode())
    sql(vision, original)
    sql(vision, f"INSERT INTO vision_gestion.comptes(utilisateur,affichage) VALUES('{OWNER}','Compte navigateur inventé'); INSERT INTO public.vision_profils(utilisateur) VALUES('{OWNER}');")
    audition_migrations = sorted((PLATFORM / "crates/audition/migrations").glob("*.sql"))
    if len(audition_migrations) != 2:
        raise Refused("AUDITION_MIGRATION_SET_REFUSED")
    for migration in audition_migrations:
        sql(vision, source(state, str(migration.relative_to(PLATFORM))))
    role = roles["audition"]
    sql(vision, f"""
      GRANT CONNECT ON DATABASE {vision} TO {role};
      GRANT USAGE ON SCHEMA audition TO {role};
      GRANT SELECT ON audition.schema_migrations,audition.administrateurs TO {role};
      GRANT SELECT,INSERT,DELETE ON audition.groupes TO {role};
      GRANT SELECT,INSERT,UPDATE,DELETE ON audition.membres TO {role};
      GRANT SELECT,INSERT,UPDATE ON audition.objets TO {role};
      GRANT SELECT,INSERT ON audition.versions,audition.requetes,audition.audit TO {role};
      GRANT USAGE,SELECT ON SEQUENCE audition.audit_id_seq TO {role};
      GRANT EXECUTE ON FUNCTION audition.est_admin(),audition.role_groupe(text) TO {role};
      INSERT INTO audition.administrateurs VALUES('{OWNER}',true);
      INSERT INTO audition.groupes VALUES('synthetic-group','Groupe entièrement inventé');
      INSERT INTO audition.membres VALUES('synthetic-group','{OWNER}','enseignant');
    """)
    private(root / "database-password", PASSWORD.encode())
    private(root / "activation-sha256", sha(b"c" * 64).encode())
    with sqlite3.connect(root / "aliases.sqlite") as connection:
        connection.execute("CREATE TABLE log_principaux(mail text,subject text)")
        connection.execute("INSERT INTO log_principaux VALUES(?,?)", ("synthetic@example.invalid", OWNER))
    (root / "aliases.sqlite").chmod(0o600)
    private(root / "tls.ext", b"basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\nsubjectAltName=DNS:log.mrj.am\n")
    run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-noenc", "-sha256", "-days", "2",
         "-subj", "/CN=MRJAM SYNTHETIC BROWSER CA", "-addext", "basicConstraints=critical,CA:TRUE",
         "-addext", "keyUsage=critical,keyCertSign,cRLSign", "-keyout", str(root / "ca.key"), "-out", str(root / "ca.pem")])
    run(["openssl", "req", "-newkey", "rsa:2048", "-noenc", "-sha256", "-subj", "/CN=log.mrj.am",
         "-keyout", str(root / "tls.key"), "-out", str(root / "tls.csr")])
    run(["openssl", "x509", "-req", "-in", str(root / "tls.csr"), "-CA", str(root / "ca.pem"),
         "-CAkey", str(root / "ca.key"), "-set_serial", "1", "-days", "2", "-sha256",
         "-extfile", str(root / "tls.ext"), "-out", str(root / "tls.pem")])
    for file in root.iterdir():
        if file.is_file():
            file.chmod(0o600)
    state["status"] = "ready"
    save(root, state)
    return state


def cleanup(root: Path, prefix: str) -> dict:
    state = json.loads((root / "fixture.json").read_bytes())
    marker = "mrjam-runtime-browser:" + prefix
    if state["prefix"] != prefix or state["marker"] != marker:
        raise Refused("FIXTURE_MARKER_REFUSED")
    expected_roles = set(role_names(prefix).values())
    expected_databases = {prefix + "_mateval", prefix + "_vision"}
    if not set(state["created_roles"]) <= expected_roles or not set(state["created_databases"]) <= expected_databases:
        raise Refused("FIXTURE_OBJECT_SET_REFUSED")
    # Check every marker before deleting any object. Do not terminate sessions:
    # the caller must first stop its CLI, otherwise cleanup visibly fails.
    for kind, names, catalog, field in (
        ("DATABASE", state["created_databases"], "pg_database", "datname"),
        ("ROLE", state["created_roles"], "pg_authid", "rolname"),
    ):
        for name in names:
            observed = sql("mrjam_synthetic", f"SELECT shobj_description(oid,'{catalog}') FROM {catalog} WHERE {field}='{name}';")
            if observed != marker:
                raise Refused("FIXTURE_OWNERSHIP_REFUSED")
    for name in list(state["created_databases"]):
        sql("mrjam_synthetic", f"DROP DATABASE {name};")
        state["created_databases"].remove(name)
        save(root, state)
    for name in list(state["created_roles"]):
        sql("mrjam_synthetic", f"DROP ROLE {name};")
        state["created_roles"].remove(name)
        save(root, state)
    state["status"] = "cleaned"
    save(root, state)
    return {"status": "cleaned", "databases": 2, "roles": len(expected_roles)}


def main() -> None:
    guard()  # Before any file read, Docker access, credential or SQL operation.
    if len(sys.argv) not in (3, 4) or sys.argv[1] not in ("setup", "cleanup"):
        raise Refused("FIXTURE_ARGUMENTS_REFUSED")
    root, prefix = workdir(sys.argv[2])
    verify_container()
    if sys.argv[1] == "setup" and len(sys.argv) == 4:
        state = setup(root, prefix, Path(sys.argv[3]))
        print(json.dumps({"status": state["status"], "migration_files": len(state["migration_sources_sha256"])}))
    elif sys.argv[1] == "cleanup" and len(sys.argv) == 3:
        print(json.dumps(cleanup(root, prefix)))
    else:
        raise Refused("FIXTURE_ARGUMENTS_REFUSED")


if __name__ == "__main__":
    try:
        main()
    except (Refused, OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(json.dumps({"code": str(error) if isinstance(error, Refused) else "FIXTURE_FAILED"}), file=sys.stderr)
        sys.exit(2)
