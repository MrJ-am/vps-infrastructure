#!/usr/bin/env python3
"""Fixed local SQLite predicates. No business values ever leave this process.

The component processes private state on the VPS after dropping root, and emits
only nonidentifying booleans. It accepts no paths, SQL, arguments or environment
configuration. Read-only transactions include committed WAL contents. This is
an observation, not permission to discard old state or mark work complete.
"""
import json
import os
from pathlib import Path
import resource
import signal
import sqlite3
import stat
import sys
import time

STATE_UID = 984
STATE_GID = 984
CYCLE = "/var/lib/mrjam-metier/cycle/courriels.sqlite"
CLOSURE = "/var/lib/mrjam-metier/fermeture/courriels.sqlite"
EXPECTED = {
    "effacements_termines": [("utilisateur", "TEXT", 0, None, 1, 0)],
    "fermetures": [("sujet", "TEXT", 0, None, 1, 0),
                   ("outils_effaces", "INTEGER", 0, None, 0, 0),
                   ("terminee", "INTEGER", 0, None, 0, 0)],
}
SQL = {
    "effacements_termines": "SELECT EXISTS(SELECT 1 FROM effacements_termines)",
    "fermetures": "SELECT EXISTS(SELECT 1 FROM fermetures), EXISTS(SELECT 1 FROM fermetures WHERE terminee IS NULL)",
}


class Refused(RuntimeError):
    pass


def inspect_database(path, table, uid=STATE_UID, gid=STATE_GID):
    """Internal testable function; production entrypoint supplies literals only."""
    if table not in EXPECTED or not Path(path).is_absolute():
        raise Refused("INPUT_REFUSED")
    for parent in reversed(Path(path).parents):
        item = parent.lstat()
        if not stat.S_ISDIR(item.st_mode):
            raise Refused("PATH_REFUSED")
    item = Path(path).lstat()
    if (not stat.S_ISREG(item.st_mode) or item.st_uid != uid or item.st_gid != gid
            or stat.S_IMODE(item.st_mode) != 0o600 or item.st_nlink != 1
            or not 0 < item.st_size <= 64 * 1024 * 1024):
        raise Refused("FILE_REFUSED")
    # URI path encoding is required even for the synthetic test directory.
    db = sqlite3.connect(Path(path).as_uri() + "?mode=ro", uri=True, timeout=1)
    try:
        deadline = time.monotonic() + 4
        steps = [0]
        def progress():
            steps[0] += 1
            return int(steps[0] > 10000 or time.monotonic() > deadline)
        db.set_progress_handler(progress, 1000)
        db.execute("PRAGMA query_only=ON")
        db.execute("PRAGMA trusted_schema=OFF")
        db.execute("BEGIN")
        entry = db.execute("SELECT type FROM sqlite_schema WHERE name=?", (table,)).fetchall()
        if not entry:
            return {"state": "observed", "marker_table_present": False, "markers_present": False,
                    **({"incomplete_present": False} if table == "fermetures" else {})}
        if entry != [("table",)]:
            raise Refused("SCHEMA_REFUSED")
        schema = [tuple(row[1:]) for row in db.execute("PRAGMA table_xinfo(" + table + ")")]
        if schema != EXPECTED[table]:
            raise Refused("SCHEMA_REFUSED")
        def authorize(action, first, second, _database, _trigger):
            if action == sqlite3.SQLITE_SELECT:
                return sqlite3.SQLITE_OK
            if action == sqlite3.SQLITE_READ and first == table and second in ("", "terminee"):
                return sqlite3.SQLITE_OK
            return sqlite3.SQLITE_DENY
        db.set_authorizer(authorize)
        values = db.execute(SQL[table]).fetchone()
        if any(type(v) is not int or v not in (0, 1) for v in values):
            raise Refused("RESULT_REFUSED")
        return {"state": "observed", "marker_table_present": True, "markers_present": bool(values[0]),
                **({"incomplete_present": bool(values[1])} if table == "fermetures" else {})}
    finally:
        db.close()


def observe(path, table):
    try:
        return inspect_database(path, table)
    except Exception:
        return {"state": "unknown"}


def timeout(_signal, _frame):
    raise Refused("TIME_LIMIT")


def main():
    if len(sys.argv) != 1 or os.geteuid() != 0:
        return 64
    try:
        os.environ.clear()
        os.umask(0o077)
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024,) * 2)
        resource.setrlimit(resource.RLIMIT_CPU, (12, 12))
        signal.signal(signal.SIGALRM, timeout)
        signal.alarm(15)
        os.setgroups([])
        os.setgid(STATE_GID)
        os.setuid(STATE_UID)
        result = {"schema_version": 1, "authority": "fixed-read-only-obligation-predicates",
                  "cycle": observe(CYCLE, "effacements_termines"),
                  "closure": observe(CLOSURE, "fermetures"),
                  "application_data_exported": False, "secret_contents_read": False,
                  "sql_mutations": False, "services_changed": False}
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0 if result["cycle"]["state"] == result["closure"]["state"] == "observed" else 65
    except Exception:
        print('{"schema_version":1,"state":"unknown","code":"OBLIGATION_PREFLIGHT_REFUSED"}')
        return 65


if __name__ == "__main__":
    raise SystemExit(main())
