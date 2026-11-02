#!/usr/bin/env python3
"""Independent invented native mail snapshots for the isolated NixOS guest."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time

sys.path.insert(0, "/etc")
from workers_fixture import command, private_file, require, sql, smtp_refuse

ROOT = Path("/var/lib/synthetic-mail-proof")
INPUT = Path("/var/lib/synthetic-mail-input")
SECRET = Path("/var/lib/synthetic-mail-credentials")
LEGACY = Path("/var/lib/mrjam-metier")
SOURCES = {"cycle.sqlite": LEGACY / "cycle/courriels.sqlite", "closure.sqlite": LEGACY / "fermeture/courriels.sqlite",
           "global.sqlite": LEGACY / "courriel/file.sqlite"}
STAGED = {"cycle.sqlite": Path("/run/mrjam-cycle-mail-adoption/mail.sqlite"),
          "closure.sqlite": Path("/run/mrjam-archive-mail-adoption/closure.sqlite"),
          "global.sqlite": Path("/run/mrjam-archive-mail-adoption/global.sqlite")}
STATES = {name: Path("/var/lib/mrjam-vision-" + name + "/courriels.sqlite") for name in ("cycle", "archive")}
MARKERS = {"cycle": [("synthetic_marker_cycle",), ("synthetic_marker_other",)],
           "archive": [("synthetic_marker_complete", 1700000000, 1700000001),
                       ("synthetic_marker_partial", 1700000000, None), ("synthetic_marker_pending", None, None)]}
SENDER = "sender@synthetic.invalid"


def normal(value):
    return json.loads(json.dumps(value))


def save(name, value):
    path = ROOT / name
    path.write_text(json.dumps(value, sort_keys=True))
    path.chmod(0o600)


def read(name):
    return json.loads((ROOT / name).read_text())


def message(key, target):
    # Fixed historical MIME syntax, deliberately folded Message-ID.
    return ("From: " + SENDER + "\r\nTo: " + target + "\r\nSubject: Synthetic retained mail\r\n"
            "Message-ID:\r\n <" + hashlib.sha256(key.encode()).hexdigest() + "@mrj.am>\r\n"
            "Date: Mon, 02 Nov 2026 00:00:00 +0000\r\nMIME-Version: 1.0\r\n"
            "Content-Type: text/plain; charset=utf-8\r\nContent-Transfer-Encoding: base64\r\n\r\n"
            + base64.b64encode(b"INVENTED-MAIL-NO-REAL-DATA").decode() + "\r\n").encode()


def source(name, keys, marker=None):
    db = sqlite3.connect(":memory:")
    db.executescript(Path("/etc/mail-adoption/schemas/native-mail.sql").read_text())
    db.execute("ALTER TABLE courriels ADD COLUMN empreinte TEXT")
    db.execute("ALTER TABLE courriels ADD COLUMN empreinte_metier TEXT")
    values = []
    for key, target in keys:
        raw = message(key, target)
        row = (key, raw, 1700000000, "attente", 2, 0, None, "relais_indisponible",
               hashlib.sha256(raw).hexdigest(), "c" * 64)
        db.execute("INSERT INTO courriels VALUES(?,?,?,?,?,?,?,?,?,?)", row)
        values.append([key, base64.b64encode(raw).decode(), *row[2:]])
    if marker:
        ddl = "cycle-markers.sql" if marker == "cycle" else "closure-markers.sql"
        db.executescript(Path("/etc/mail-adoption/schemas", ddl).read_text())
        table, parameters = ("effacements_termines", "?") if marker == "cycle" else ("fermetures", "?,?,?")
        db.executemany("INSERT INTO " + table + " VALUES(" + parameters + ")", MARKERS[marker])
    db.commit()
    raw = db.serialize()
    db.close()
    private_file(INPUT / name, raw, gid=945 if marker == "cycle" else 943, mode=0o440)
    private_file(ROOT / name, raw)
    target = SOURCES[name]
    target.parent.mkdir(mode=0o700, exist_ok=True)
    os.chown(target.parent, 984, 984)
    private_file(target, raw, gid=984, mode=0o600)
    os.chown(target, 984, 984)
    return values


def prepare():
    require(os.getuid() == 0 and not ROOT.exists(), "SYNTHETIC_SCOPE")
    for directory in (ROOT, INPUT, SECRET):
        directory.mkdir(mode=0o700)
    LEGACY.mkdir(mode=0o700, exist_ok=True)
    os.chown(LEGACY, 984, 984)
    command(["runuser", "-u", "postgres", "--", "createdb", "vision"])
    command(["runuser", "-u", "postgres", "--", "createdb", "vision_journal"])
    sql("CREATE EXTENSION vector")
    for path in sorted(Path("/etc/worker-sql/migrations").glob("[0-9]*.sql")):
        sql(path.read_text())
    sql(Path("/etc/worker-sql/roles.sql").read_text())
    names = ["writer", "import", "archiviste", "rejeu", "fermeture"]
    sql("CREATE ROLE vision_journal_owner NOLOGIN NOSUPERUSER NOBYPASSRLS;" + "".join(
        "CREATE ROLE vision_journal_" + name + " LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT;"
        for name in names), "vision_journal")
    for path in sorted(Path("/etc/worker-sql/journal").glob("[0-9]*.sql")):
        sql(path.read_text(), "vision_journal")
    sql("REVOKE ALL ON DATABASE vision_journal FROM PUBLIC; GRANT CONNECT ON DATABASE vision_journal TO "
        + ",".join("vision_journal_" + name for name in names), "vision_journal")
    sql("INSERT INTO vision_gestion.comptes(utilisateur,affichage) VALUES('synthetic_marker_cycle','Invented preserved account');")
    cycle = source("cycle.sqlite", [("preavis:synthetic-old", "cycle@synthetic.invalid")], "cycle")
    shared = ("global-shared", "shared@synthetic.invalid")
    closure = source("closure.sqlite", [("fermeture:" + "a" * 64, "archive@synthetic.invalid"), shared], "archive")
    global_ = source("global.sqlite", [("global-kept", "global@synthetic.invalid"), shared])
    admission = LEGACY / "admission"
    admission.mkdir(mode=0o700)
    os.chown(admission, 984, 984)
    for filename, schema in (("admissions.sqlite", "native-requests.sql"), ("courriels.sqlite", "native-mail.sql")):
        path = admission / filename
        with sqlite3.connect(path) as db:
            db.executescript(Path("/etc/native-adoption/schemas", schema).read_text())
        path.chmod(0o600)
        os.chown(path, 984, 984)
    save("mail.json", {"cycle": sorted(cycle), "archive": sorted({row[0]: row for row in closure + global_}.values())})
    save("source-hashes.json", {name: hashlib.sha256((INPUT / name).read_bytes()).hexdigest()
                                for name in ("cycle.sqlite", "closure.sqlite", "global.sqlite")})
    private_file(SECRET / "smtp.json", json.dumps({"host": "smtp.protonmail.ch", "port": 587, "username": SENDER,
        "password": "SyntheticSMTPOnly1234567890", "from_address": SENDER, "starttls_required": True, "certificate_verification": True}))
    private_file(SECRET / "cycle.token", "SyntheticNativeOnlyToken1234567890")
    private_file(SECRET / "recipient", "archive@synthetic.invalid")
    for suffix in ("", "-initialize"):
        unit = "mrjam-vision-archive" + suffix
        configuration = {"schema_version": 1, "journal_database": "vision_journal",
            "state_file": str(STATES["archive"]), "smtp_file": "/run/credentials/" + unit + ".service/smtp",
            "recipient_file": "/run/credentials/" + unit + ".service/recipient",
            "age_program": str(Path(os.environ["SYNTHETIC_AGE_PACKAGE"]) / "bin/age"),
            "age_recipient": Path("/etc/synthetic-age/recipient").read_text().strip()}
        private_file(SECRET / ("archive" + suffix + ".json"), json.dumps(configuration))


def stage():
    # The controller, not the staging helper, must establish quiescence first.
    for unit in ("mrjam-vision-cycle", "mrjam-vision-archive"):
        require(command(["systemctl", "show", unit, "-p", "MainPID", "--value"]).strip() == b"0", "SOURCE_WRITER_STILL_ACTIVE")
    sys.path.insert(0, "/etc/staging-helper")
    from stage_adoption import prepare as prepare_images
    prepare_images()
    for name, path in STAGED.items():
        info = path.stat()
        uid = 945 if name == "cycle.sqlite" else 943
        require(info.st_uid == 0 and info.st_gid == uid and info.st_mode & 0o777 == 0o440, "STAGING_METADATA")
        require(path.parent.stat().st_uid == uid and path.parent.stat().st_mode & 0o777 == 0o700, "STAGING_PARENT")
        with sqlite3.connect(path) as db:
            require(db.execute("PRAGMA quick_check").fetchall() == [("ok",)], "STAGING_INTEGRITY")


def check(mode="initial"):
    original = read("mail.json")
    for profile, path in STATES.items():
        item = path.stat()
        uid = 945 if profile == "cycle" else 943
        require(item.st_uid == item.st_gid == uid and item.st_mode & 0o777 == 0o600 and item.st_nlink == 1, "MAIL_TARGET_OWNER")
        with sqlite3.connect(path) as db:
            table = "effacements_termines" if profile == "cycle" else "fermetures"
            markers = db.execute("SELECT * FROM " + table + " ORDER BY 1 COLLATE BINARY").fetchall()
            require(normal(markers) == normal(MARKERS[profile]), "MAIL_MARKERS_CHANGED")
            rows = db.execute("SELECT cle,message,cree,etat,essais,prochain,accepte,erreur,empreinte,contenu_sha256,empreinte_metier FROM courriels ORDER BY cle").fetchall()
            require(len(rows) == len(original[profile]), "MAIL_DEDUP_OR_ROW_LOSS")
            for row, expected in zip(rows, original[profile], strict=True):
                require([row[0], base64.b64encode(row[1]).decode(), row[2], row[8], row[9], row[10]]
                        == [expected[0], expected[1], expected[2], expected[8], None, expected[9]], "MAIL_BYTES_OR_PROOFS_CHANGED")
                if mode == "initial":
                    require(list(row[3:8]) == expected[3:8], "MAIL_RETRY_METADATA_CHANGED_DURING_ADOPTION")
                elif mode == "retry":
                    require(row[3] == "attente" and row[4] > 2 and row[5] > int(time.time()), "OLD_MAIL_NOT_DRAINED_OR_NOT_RETRIABLE")
                elif mode == "received":
                    require(row[3] == "accepte_relais" and isinstance(row[6], int), "INVENTED_RECEIPT_NOT_PRESERVED")
        require(sql("SELECT (NOT EXISTS(SELECT FROM vision_effacements.demandes) AND NOT EXISTS(SELECT FROM vision_effacements.fermetures))::int", "vision_journal") == "1", "MARKER_OR_KEY_INVENTED_SQL_INTENTION")
    require(sql("SELECT count(*) FROM vision_gestion.comptes WHERE utilisateur='synthetic_marker_cycle'") == "1", "MARKER_INFERRED_ERASURE")
    for name, digest in read("source-hashes.json").items():
        require(hashlib.sha256((INPUT / name).read_bytes()).hexdigest() == digest, "SOURCE_MODIFIED")
        require(hashlib.sha256(SOURCES[name].read_bytes()).hexdigest() == digest, "LEGACY_SOURCE_MODIFIED")


def remember():
    save("published.json", {name: {"inode": path.stat().st_ino, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                            for name, path in STATES.items()})


def unchanged():
    for name, before in read("published.json").items():
        path = STATES[name]
        require(path.stat().st_ino == before["inode"] and hashlib.sha256(path.read_bytes()).hexdigest() == before["sha256"], "REFUSAL_OR_REPEAT_CHANGED_TARGET")


def change_marker():
    with sqlite3.connect(STAGED["cycle.sqlite"]) as db:
        db.execute("INSERT INTO effacements_termines VALUES('synthetic_extra_marker')")


def change_collision():
    with sqlite3.connect(STAGED["global.sqlite"]) as db:
        db.execute("UPDATE courriels SET essais=3 WHERE cle='global-shared'")


def restore():
    for name in ("cycle.sqlite", "closure.sqlite", "global.sqlite"):
        private_file(STAGED[name], (ROOT / name).read_bytes(), gid=945 if name == "cycle.sqlite" else 943, mode=0o440)


def receive():
    for path in STATES.values():
        with sqlite3.connect(path) as db:
            db.execute("UPDATE courriels SET etat='accepte_relais',accepte=?,erreur=NULL", (int(time.time()),))


def no_leak():
    unit = command(["systemctl", "cat", "mrjam-vision-archive.service"])
    recipient = Path("/etc/synthetic-age/recipient").read_text().strip().encode()
    require(recipient not in unit and b"/run/credentials/mrjam-vision-archive.service/configuration" in unit, "ARCHIVE_CONFIGURATION_NOT_PRIVATE")
    data = command(["journalctl", "--no-pager", "-o", "cat", "-u", "mrjam-cycle-mail-adopt", "-u", "mrjam-archive-mail-adopt",
                    "-u", "mrjam-vision-cycle", "-u", "mrjam-vision-archive"])
    for marker in (b"SyntheticSMTPOnly1234567890", b"synthetic_marker_", b"INVENTED-MAIL-NO-REAL-DATA", b"@synthetic.invalid", recipient):
        require(marker not in data, "PRIVATE_MAIL_DIAGNOSTIC")


ACTIONS = {"prepare": prepare, "check": check, "remember": remember, "unchanged": unchanged,
           "stage": stage,
           "change-marker": change_marker, "change-collision": change_collision, "restore": restore,
           "retry": lambda: check("retry"), "received": lambda: check("received"), "receive": receive,
           "no-leak": no_leak, "smtp-refuse": smtp_refuse}
if __name__ == "__main__":
    try:
        require(len(sys.argv) == 2 and sys.argv[1] in ACTIONS, "SYNTHETIC_MAIL_SCOPE")
        ACTIONS[sys.argv[1]]()
    except Exception as error:
        code = str(error) if isinstance(error, RuntimeError) and re.fullmatch(r"[A-Z0-9_]+", str(error)) else type(error).__name__
        print("SYNTHETIC_MAIL_TEST_FAILED:" + code, file=sys.stderr)
        raise SystemExit(1)
