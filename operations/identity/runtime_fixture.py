#!/usr/bin/env python3
"""Only for the new, synthetic NixOS guest in runtime-systemd.nix."""
import errno
import hashlib
import http.client
import json
import os
from pathlib import Path
import socket
import sqlite3
import stat
import subprocess
import sys
import time
from types import SimpleNamespace
from urllib.parse import urlsplit

sys.path.insert(0, "/etc/identity-native-fixture")
from qualify import Native
from fixture import ALICE, BOB, ISSUER, canonical_json

STATE = Path("/var/lib/mrjam-metier/log/sessions.sqlite")
REFERENCE = Path("/var/lib/synthetic-identity-reference")
PUBLIC = Path("/run/synthetic-identity")
DESTINATION = Path("/run/mrjam-identity/aliases.sqlite")
SOCKET = "/run/mrjam-identity/admission.sock"


def require(condition, code):
    if not condition:
        raise RuntimeError(code)


def sql(statement):
    result = subprocess.run(["runuser", "-u", "postgres", "--", "psql", "-X", "-w", "-q", "-A", "-t",
                             "-h", "/run/postgresql", "-d", "vision", "-v", "ON_ERROR_STOP=1"],
                            input=statement.encode(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
    require(result.returncode == 0, "SYNTHETIC_SQL_FAILED")
    return result.stdout.decode().strip()


def state_snapshot():
    with sqlite3.connect("file:" + str(STATE) + "?mode=ro", uri=True) as db:
        schema = db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall()
        policies = db.execute("SELECT * FROM log_principaux ORDER BY subject").fetchall()
    item = STATE.stat()
    sentinel = Path("/var/lib/mrjam-metier/unrelated-owner-marker").stat()
    return {"schema": schema, "policies": policies, "uid": item.st_uid, "gid": item.st_gid,
            "mode": stat.S_IMODE(item.st_mode), "sentinel_uid": sentinel.st_uid, "sentinel_gid": sentinel.st_gid}


def prepare_state():
    require(os.getuid() == 0 and not STATE.exists(), "SYNTHETIC_STATE_ALREADY_PRESENT")
    REFERENCE.mkdir(mode=0o700)
    PUBLIC.mkdir(mode=0o755)
    STATE.parent.mkdir(parents=True, mode=0o700)
    for directory in (STATE.parent.parent, STATE.parent):
        directory.chmod(0o700)
        os.chown(directory, 984, 984)
    marker = STATE.parent.parent / "unrelated-owner-marker"
    marker.write_text("SYNTHETIC-UNRELATED-OWNER")
    marker.chmod(0o400)
    os.chown(marker, 949, 949)
    with sqlite3.connect(STATE) as db:
        db.executescript(Path("/etc/identity-native-fixture/legacy-state.sql").read_text())
        now = int(time.time())
        db.executemany("INSERT INTO log_principaux VALUES(?,?,?,?,?)", [
            (ALICE, "alice@synthetic.invalid", 604800, "mfa", now - 60),
            (BOB, "bob@synthetic.invalid", 2592000, "any", now - 60)])
        db.execute("INSERT INTO log_sessions VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (
            "a" * 64, "vision.mrj.am", ALICE, "synthetic_alice", "SYNTHETIC-CSRF", now, now, now + 3600,
            now, "SYNTHETIC-PRIVATE-ACCESS", "SYNTHETIC-PRIVATE-REFRESH", "SYNTHETIC-PRIVATE-NONCE"))
    STATE.chmod(0o600)
    os.chown(STATE, 984, 984)
    (REFERENCE / "state-before.json").write_text(json.dumps(state_snapshot(), sort_keys=True))
    sql(Path("/etc/identity-native-fixture/principals.sql").read_text())


def native_client():
    native = object.__new__(Native)
    native.package = Path(os.environ["SYNTHETIC_KANIDM_PACKAGE"])
    native.config = Path("/etc/kanidm/server.toml")
    native.crypto = SimpleNamespace(ca=Path("/etc/synthetic-identity-tls/ca.pem"))
    native.port = 8443
    return native


def prepare_native():
    native = native_client()
    admin = native.login("idm_admin", native.recover("idm_admin"), True)
    native.api("/v1/person", {"attrs": {"name": ["synthetic_native_alice"], "displayname": ["Synthetic Runtime Alice"],
                                       "mail": ["native@synthetic.invalid"]}}, bearer=admin)
    subject = native.api("/v1/person/synthetic_native_alice", bearer=admin)["attrs"]["uuid"][0]
    native.api("/v1/oauth2/_basic", {"attrs": {"name": ["mrjam-vision"], "displayname": ["Synthetic runtime"],
                                              "oauth2_rs_origin_landing": ["https://vision.mrj.am/"],
                                              "oauth2_strict_redirect_uri": ["true"]}}, bearer=admin)
    native.api("/v1/oauth2/mrjam-vision/_attr/oauth2_rs_origin",
               ["https://vision.mrj.am/auth/retour", "https://audition.mrj.am/auth/retour"], bearer=admin)
    native.api("/v1/oauth2/mrjam-vision/_scopemap/idm_all_persons", ["openid", "profile", "email"], bearer=admin)
    secret = native.api("/v1/oauth2/mrjam-vision/_basic_secret", bearer=admin)
    user = native.login("synthetic_native_alice", native.recover("synthetic_native_alice"), False)
    credentials = Path("/var/lib/mrjam-identite")
    credentials.mkdir(mode=0o700)
    credential = credentials / "kanidm-vision.secret"
    credential.write_text(secret)
    credential.chmod(0o400)
    sql("INSERT INTO public.synthetic_principals VALUES ('" + ISSUER + "','" + subject + "','synthetic_runtime_alice',true,false);")
    (PUBLIC / "subject").write_text(subject)
    (PUBLIC / "subject").chmod(0o444)
    (REFERENCE / "native.json").write_text(json.dumps({"subject": subject, "bearer": user, "secret": secret}))


def prove_credential():
    require(os.getuid() == 984, "WRONG_BROKER_UID")
    copy = Path("/run/credentials/mrjam-identity.service/kanidm-vision")
    item = copy.stat()
    parent = copy.parent.stat()
    Path("/run/mrjam-identity/credential-metadata.json").write_text(json.dumps({
        "uid": item.st_uid, "gid": item.st_gid, "mode": stat.S_IMODE(item.st_mode), "process_uid": os.getuid(),
        "parent_uid": parent.st_uid, "parent_gid": parent.st_gid, "parent_mode": stat.S_IMODE(parent.st_mode),
        "mount_readonly": bool(os.statvfs(copy).f_flag & os.ST_RDONLY),
        "credential_directory_matches": os.environ.get("CREDENTIALS_DIRECTORY") == str(copy.parent)}))
    # systemd260 uses root-owned0440 with a named ACL for the unit UID.
    # Check effective access and immutability, rather than requiring a chown.
    require(stat.S_ISREG(item.st_mode) and item.st_uid in (0, 984)
            and not stat.S_IMODE(item.st_mode) & 0o227 and item.st_size > 0, "CREDENTIAL_COPY_PERMISSIONS")
    require(copy.read_bytes(), "EMPTY_CREDENTIAL_COPY")
    try:
        descriptor = os.open(copy, os.O_WRONLY)
    except OSError as error:
        require(error.errno in (errno.EACCES, errno.EROFS), "UNEXPECTED_CREDENTIAL_WRITE_ERROR")
    else:
        os.close(descriptor)
        raise RuntimeError("CREDENTIAL_COPY_WRITABLE")
    try:
        descriptor = os.open("/var/lib/mrjam-identite/kanidm-vision.secret", os.O_RDONLY)
    except PermissionError:
        pass
    else:
        os.close(descriptor)
        raise RuntimeError("SOURCE_SECRET_READABLE_BY_BROKER")
    Path("/run/mrjam-identity/credential-proof").write_text("verified")


def prove_readonly():
    require(os.getuid() == 984, "WRONG_PROJECTION_UID")
    try:
        descriptor = os.open(STATE, os.O_WRONLY)
    except OSError as error:
        require(error.errno == errno.EROFS, "SOURCE_NOT_READONLY_MOUNT")
    else:
        os.close(descriptor)
        raise RuntimeError("PROJECTION_SOURCE_WRITABLE")


def check_adoption():
    before = json.loads((REFERENCE / "state-before.json").read_text())
    after = json.loads(json.dumps(state_snapshot()))
    require(before == after, "STARTUP_MODIFIED_RETAINED_STATE_OR_OWNER")
    require(after["uid"] == after["gid"] == 984 and after["mode"] == 0o600, "SOURCE_PERMISSIONS")


def check_projection(expected):
    require(os.getuid() == 941, "WRONG_READER_UID")
    with sqlite3.connect("file:" + str(DESTINATION) + "?mode=ro", uri=True) as db:
        objects = db.execute("SELECT name,type FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
        require(objects == [("log_principaux", "table")], "PROJECTION_EXPOSES_OTHER_OBJECTS")
        columns = db.execute("PRAGMA table_info(log_principaux)").fetchall()
        require([row[1] for row in columns] == ["subject", "mail"], "PROJECTION_EXPOSES_OTHER_COLUMNS")
        require(db.execute("SELECT count(*) FROM log_principaux").fetchone()[0] == expected, "PROJECTION_ROW_COUNT")
    item = DESTINATION.stat()
    require(item.st_uid == 984 and item.st_gid == 940 and stat.S_IMODE(item.st_mode) == 0o640, "PROJECTION_OWNERSHIP")
    try:
        sqlite3.connect("file:" + str(STATE) + "?mode=ro", uri=True)
    except sqlite3.OperationalError:
        pass
    else:
        raise RuntimeError("READER_ACCESSES_PRIVATE_SOURCE")


def watch_projection():
    subject = (PUBLIC / "subject").read_text()
    with sqlite3.connect("file:" + str(DESTINATION) + "?mode=ro", uri=True) as db:
        inode = DESTINATION.stat().st_ino
        Path("/run/synthetic-alias-reader/opened").write_text(str(inode))
        end = time.monotonic() + 40
        while time.monotonic() < end:
            if db.execute("SELECT mail FROM log_principaux WHERE subject=?", (subject,)).fetchone() == ("native@synthetic.invalid",):
                require(DESTINATION.stat().st_ino == inode, "PROJECTION_REPLACED_OPEN_INODE")
                Path("/run/synthetic-alias-reader/observed").write_text("stable-inode-refresh")
                return
            time.sleep(.2)
    raise RuntimeError("OPEN_READER_DID_NOT_OBSERVE_REFRESH")


def register(allowed):
    subject = (PUBLIC / "subject").read_text()
    body = canonical_json({"issuer": ISSUER, "subject": subject, "mail": "native@synthetic.invalid"}) + b"\n"
    with socket.socket(socket.AF_UNIX) as connection:
        connection.settimeout(5)
        connection.connect(SOCKET)
        try:
            connection.sendall(body)
            connection.shutdown(socket.SHUT_WR)
            answer = connection.recv(2048)
        except (ConnectionResetError, BrokenPipeError):
            answer = b""
    if allowed:
        require(answer == b'{"status":"registered"}\n', "ADMISSION_REGISTRATION_FAILED")
    else:
        require(answer in (b"", b'{"error":"registration_refused"}\n'), "WRONG_UID_REGISTRATION_NOT_REFUSED")


def check_registration(custom):
    subject = (PUBLIC / "subject").read_text()
    with sqlite3.connect(STATE) as db:
        row = db.execute("SELECT subject,mail,duration,minimum,qualified_after FROM log_principaux WHERE subject=?", (subject,)).fetchone()
    require(row is not None and row[:2] == (subject, "native@synthetic.invalid"), "REGISTRATION_MAPPING_MISSING")
    require(row[2:4] == ((2592000, "mfa") if custom else (604800, "any")), "REGISTRATION_POLICY_CHANGED")
    require(int(time.time()) - 120 <= row[4] <= int(time.time()), "REGISTRATION_QUALIFICATION_TIME")


def custom_policy():
    subject = (PUBLIC / "subject").read_text()
    with sqlite3.connect(STATE) as db:
        db.execute("UPDATE log_principaux SET duration=2592000,minimum='mfa' WHERE subject=?", (subject,))


def broker(path, cookie=None):
    connection = http.client.HTTPConnection("127.0.0.1", 3002, timeout=15)
    headers = {"Host": "mrj-auth.internal", "X-Forwarded-Host": "vision.mrj.am",
               "X-Forwarded-Proto": "https", "X-Original-Method": "GET"}
    if cookie:
        headers["Cookie"] = cookie
    try:
        connection.request("GET", path, headers=headers)
        response = connection.getresponse()
        return response.status, response.getheaders(), response.read()
    finally:
        connection.close()


def native_login():
    reference = json.loads((REFERENCE / "native.json").read_text())
    status, headers, data = broker("/auth/connexion?retour=%2F")
    require(status == 302, "SYSTEMD_LOGIN_START")
    values = {name.lower(): value for name, value in headers}
    redirect = native_client().authorize(urlsplit(values["location"]).query, reference["bearer"])
    status, headers, data = broker("/auth/retour?" + urlsplit(redirect).query, values["set-cookie"].split(";", 1)[0])
    require(status == 302, "SYSTEMD_NATIVE_CALLBACK")
    session = [value.split(";", 1)[0] for name, value in headers if name.lower() == "set-cookie" and value.startswith("__Host-mrj_session=")]
    require(len(session) == 1, "SYSTEMD_NATIVE_SESSION")
    status, headers, data = broker("/verify", session[0])
    require(status == 204 and dict((name.lower(), value) for name, value in headers)["x-mrj-user"] == "synthetic_runtime_alice", "SYSTEMD_NATIVE_VERIFY")
    (REFERENCE / "session-cookie").write_text(session[0])


def after_restart():
    status, headers, data = broker("/verify", (REFERENCE / "session-cookie").read_text())
    require(status == 204 and dict((name.lower(), value) for name, value in headers)["x-mrj-user"] == "synthetic_runtime_alice", "RESTART_LOST_NATIVE_SESSION")


def no_secret_journal():
    reference = json.loads((REFERENCE / "native.json").read_text())
    result = subprocess.run(["journalctl", "--no-pager", "-o", "cat", "-u", "mrjam-identity.service",
                             "-u", "mrjam-identity-aliases.service"], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=10)
    require(result.returncode == 0, "JOURNAL_CHECK_FAILED")
    sensitive = [reference["subject"], reference["secret"], reference["bearer"], "SYNTHETIC-PRIVATE-ACCESS",
                 "SYNTHETIC-PRIVATE-REFRESH", "native@synthetic.invalid"]
    with sqlite3.connect("file:" + str(STATE) + "?mode=ro", uri=True) as db:
        for row in db.execute("SELECT access,refresh,nonce,csrf FROM log_sessions"):
            sensitive.extend(row)
    require(all(value.encode() not in result.stdout for value in sensitive), "PRIVATE_VALUE_IN_UNIT_JOURNAL")


if __name__ == "__main__":
    actions = {"prepare-state": prepare_state, "prepare-native": prepare_native,
               "prove-credential": prove_credential, "prove-readonly": prove_readonly,
               "check-adoption": check_adoption, "check-projection-two": lambda: check_projection(2),
               "check-projection-three": lambda: check_projection(3), "watch-projection": watch_projection,
               "register": lambda: register(True), "wrong-registration": lambda: register(False),
               "check-registration": lambda: check_registration(False), "custom-policy": custom_policy,
               "check-custom-policy": lambda: check_registration(True), "native-login": native_login,
               "after-restart": after_restart, "no-secret-journal": no_secret_journal}
    try:
        require(len(sys.argv) == 2 and sys.argv[1] in actions, "UNKNOWN_FIXTURE_ACTION")
        actions[sys.argv[1]]()
        print("SYNTHETIC_CHECK_PASSED")
    except Exception as error:
        code = "SYNTHETIC_CHECK_FAILED_" + (str(error) if isinstance(error, RuntimeError) else type(error).__name__)
        if os.getuid() == 984:
            try:
                Path("/run/mrjam-identity/fixture-error-code").write_text(code)
            except OSError:
                pass
        print(code)
        raise SystemExit(1)
