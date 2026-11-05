"""Versioned migration plans. SQL results and credentials are never logged.

SQL steps are transactional and recorded under the same database lock. Longer
or incompatible operations use a tested program supplied by the release.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

LEDGER = Path("/var/lib/mrjam-delivery/migration-receipts.json")


def receipt(step, root):
    values = json.loads(LEDGER.read_text()) if LEDGER.exists() else {}
    value = values.get(step["id"])
    if value is not None and value["checksum"] != digest(step, root):
        raise RuntimeError("An executed migration definition has changed")
    return value


def record(step, root, phase, metadata=None):
    values = json.loads(LEDGER.read_text()) if LEDGER.exists() else {}
    receipt(step, root)
    values[step["id"]] = {**values.get(step["id"], {}), **(metadata or {}),
                           "checksum": digest(step, root), "phase": phase}
    temporary = LEDGER.with_suffix(".tmp")
    with temporary.open("w") as stream:
        json.dump(values, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(LEDGER)


def pending_programs(plan, root):
    result = []
    for step in plan["steps"]:
        if step["driver"] == "program":
            previous = receipt(step, root)
            if previous is None or previous["phase"] != "complete":
                result.append(step["id"])
    return result


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", value):
        raise ValueError("Invalid migration identifier")
    return value


def source_file(root, name):
    path = (root / name).resolve(strict=True)
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError("Migration file outside its release")
    return path


def validate_sql(text):
    # Ignore literals/comments, including PL/pgSQL bodies, then reject transaction
    # commands and psql commands. END/ABORT are PostgreSQL synonyms for COMMIT/ROLLBACK.
    tokens = re.sub(r"--[^\n]*|/\*.*?\*/|'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|"
                    r"(?P<dollar>\$(?:[A-Za-z_][A-Za-z0-9_]*)?\$).*?(?P=dollar)",
                    " ", text, flags=re.DOTALL)
    if "\\" in tokens or re.search(
            r"\b(?:BEGIN|COMMIT|END|ROLLBACK|ABORT|SAVEPOINT|RELEASE)\b|"
            r"\b(?:START|PREPARE|SET)\s+TRANSACTION\b", tokens, re.IGNORECASE):
        raise ValueError("SQL migrations must not control their transaction or psql")


def load(path):
    path = Path(path)
    plan = json.loads(path.read_text())
    if plan.get("version") != 1 or not isinstance(plan.get("steps"), list):
        raise ValueError("Invalid migration plan")
    seen = set()
    for step in plan["steps"]:
        key = identifier(step["id"])
        if key in seen:
            raise ValueError("Duplicate migration")
        seen.add(key)
        if step.get("compatibility") not in ["both", "maintenance"]:
            raise ValueError("Migration compatibility must be explicit")
        if step.get("phase", "before-system") not in ["before-system", "after-system"]:
            raise ValueError("Unknown migration phase")
        for unit in step.get("hold_units", []):
            if not re.fullmatch(r"[a-z][a-z0-9_-]*", unit) or unit in ["mrjam-ci", "mrjam-delivery", "mrjam-delivery-restore"]:
                raise ValueError("Invalid migration-held service")
        if not isinstance(step.get("destructive", False), bool):
            raise ValueError("Invalid destructive migration declaration")
        if step["driver"] == "sql":
            if step["compatibility"] != "both":
                raise ValueError("Incompatible migrations require a tested recovery program")
            identifier(step["database"])
            for field in ["sql", "checks", "fixture"]:
                text = source_file(path.parent, step[field]).read_text()
                validate_sql(text)
        elif step["driver"] == "program":
            package = step["package"]
            if not re.fullmatch(r"/nix/store/[0-9a-z]{32}-[A-Za-z0-9+._-]+", package):
                raise ValueError("Expected a built migration program")
            for action in ["check", "apply", "verify", "recover"]:
                if not Path(package, "bin", action).is_file():
                    raise ValueError("Migration program lacks " + action)
            if step["compatibility"] == "maintenance":
                for action in ["quiesce", "resume"]:
                    if not Path(package, "bin", action).is_file():
                        raise ValueError("Maintenance program lacks " + action)
        else:
            raise ValueError("Unknown migration driver")
    if any(step["driver"] == "sql" for step in plan["steps"]):
        source_file(path.parent, plan["compatibility_check"])
    return plan


def digest(step, root):
    data = json.dumps(step, sort_keys=True).encode()
    if step["driver"] == "sql":
        data += source_file(root, step["sql"]).read_bytes()
        data += source_file(root, step["checks"]).read_bytes()
    return hashlib.sha256(data).hexdigest()


def sql_transaction(step, root):
    key = identifier(step["id"])
    checksum = digest(step, root)
    sql = source_file(root, step["sql"]).read_text()
    checks = source_file(root, step["checks"]).read_text()
    validate_sql(sql)
    validate_sql(checks)
    return f"""BEGIN;
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '60s';
SELECT pg_advisory_xact_lock(683294517);
CREATE SCHEMA IF NOT EXISTS mrjam_delivery;
CREATE TABLE IF NOT EXISTS mrjam_delivery.migrations
 (id text PRIMARY KEY, checksum text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now());
SELECT EXISTS(SELECT 1 FROM mrjam_delivery.migrations WHERE id='{key}') AS already_applied \\gset
\\if :already_applied
DO $mrjam$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM mrjam_delivery.migrations WHERE id='{key}' AND checksum='{checksum}')
 THEN RAISE EXCEPTION 'Applied migration has changed'; END IF;
END $mrjam$;
\\else
{sql}
{checks}
INSERT INTO mrjam_delivery.migrations(id, checksum) VALUES ('{key}', '{checksum}');
\\endif
COMMIT;
"""


def psql(database, text, executable, test_url=None):
    if test_url is not None:
        # Test callers supply the synthetic fixture; production always uses peer.
        if not test_url.startswith("postgresql://mrjam_synthetic:") or "@127.0.0.1:55432/" not in test_url:
            raise ValueError("Expected the synthetic PostgreSQL fixture")
        arguments = [executable, "--dbname", test_url]
    else:
        arguments = ["runuser", "-u", "postgres", "--", executable, "--host", "/run/postgresql", "--dbname", identifier(database)]
    subprocess.run(arguments + ["-X", "-q", "-v", "ON_ERROR_STOP=1"],
                   input=text, text=True, check=True, timeout=180,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def authorize(plan, revision, approvals, root=None):
    destructive = []
    for step in plan["steps"]:
        if step.get("destructive", False):
            previous = receipt(step, root) if root is not None else None
            if previous is None or previous["phase"] != "complete":
                destructive.append(step["id"])
    if destructive:
        path = Path(approvals, revision + ".json")
        if not path.is_file():
            raise RuntimeError("Destructive migration requires explicit authorization and recovery")
        approval = json.loads(path.read_text())
        if (approval.get("revision") != revision or approval.get("migrations") != destructive
                or not approval.get("recovery_tested")):
            raise RuntimeError("Migration authorization does not match this release")


def prepare(path, revision, approvals, schema_digests=None, stateful_versions=None):
    plan = load(path)
    root = Path(path).parent
    authorize(plan, revision, approvals, root=root)
    for step in plan["steps"]:
        if step["driver"] != "program":
            continue
        previous = receipt(step, root)
        if previous is not None and previous["phase"] == "complete":
            continue
        scope = step.get("scope", "server")
        record(step, root, "started", {"schema_after": (schema_digests or {}).get(scope),
                                      "stateful_after": (stateful_versions or {}).get(scope)})
        if step["compatibility"] == "maintenance":
            run_program(step, "quiesce")
    return plan


def apply(path, executable, revision, approvals, schema_digests=None, stateful_versions=None, phase=None):
    plan = load(path)
    root = Path(path).parent
    authorize(plan, revision, approvals, root=root)
    if phase is None:
        prepare(path, revision, approvals, schema_digests, stateful_versions)
    for step in plan["steps"]:
        if phase is not None and step.get("phase", "before-system") != phase:
            continue
        previous = receipt(step, root)
        scope = step.get("scope", "server")
        metadata = {"schema_after": (schema_digests or {}).get(scope),
                    "stateful_after": (stateful_versions or {}).get(scope)}
        if step["driver"] == "sql":
            psql(step["database"], sql_transaction(step, root), executable)
            record(step, root, "complete", metadata)
        else:
            if previous is not None and previous["phase"] == "complete":
                continue
            record(step, root, "started", metadata)
            # apply/recover must be resumable; the program owns its durable ledger.
            for action in ["apply", "verify"]:
                run_program(step, action)
            record(step, root, "applied")
    return plan


def run_program(step, action):
    subprocess.run([step["package"] + "/bin/" + action], check=True, timeout=1800,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def quiesce(path, selected):
    for step in load(path)["steps"]:
        if step["id"] in selected and step["compatibility"] == "maintenance":
            run_program(step, "quiesce")


def resume(path):
    root = Path(path).parent
    for step in load(path)["steps"]:
        if step["driver"] == "program":
            previous = receipt(step, root)
            if previous is None or previous["phase"] != "applied":
                continue
            if step["compatibility"] == "maintenance":
                run_program(step, "resume")
            record(step, root, "complete")


def recover(path):
    plan = load(path)
    root = Path(path).parent
    for step in reversed(plan["steps"]):
        if step["compatibility"] == "maintenance":
            if step["driver"] != "program":
                raise RuntimeError("An incompatible SQL migration requires a recovery program")
            previous = receipt(step, root)
            if previous is not None and previous["phase"] in ["started", "applied"]:
                run_program(step, "recover")
                record(step, root, "recovered")


def compatible(plan, root=None):
    for step in plan["steps"]:
        previous = receipt(step, root) if root is not None else None
        if step["compatibility"] != "both" and (previous is None or previous["phase"] != "complete"):
            return False
    return True
