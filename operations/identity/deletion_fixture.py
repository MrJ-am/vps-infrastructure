#!/usr/bin/env python3
"""Independent invented HTTP deletion through the unchanged server ELF."""
import email
import email.policy
from http.client import HTTPConnection
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time
from urllib.parse import urlsplit

sys.path.insert(0, "/etc")
import workers_fixture as worker
from workers_fixture import command, require, sql, native, ISSUER

ROOT = Path("/var/lib/synthetic-deletion")
USER = "synthetic_web_delete"
PERSON = "synthetic_native_alice"
MAIL = "deletion@synthetic.invalid"


def save(name, value):
    path = ROOT / name
    path.write_text(json.dumps(value, sort_keys=True))
    path.chmod(0o600)


def read(name):
    return json.loads((ROOT / name).read_text())


def http(path, body=None, *, port=38101, headers=None, method=None):
    values = {"Host": "vision.mrj.am", "Connection": "close"}
    if port == 3002:
        values.update({"Host": "mrj-auth.internal", "X-Forwarded-Host": "vision.mrj.am",
                       "X-Forwarded-Proto": "https", "X-Original-Method": "GET"})
    values.update(headers or {})
    wire = json.dumps(body).encode() if body is not None else None
    if wire is not None:
        values["Content-Type"] = "application/json"
    connection = HTTPConnection("127.0.0.1", port, timeout=15)
    try:
        connection.request(method or ("POST" if wire is not None else "GET"), path, wire, values)
        response = connection.getresponse()
        data = response.read(65537)
        require(len(data) <= 65536, "DELETION_RESPONSE_LIMIT")
        return response.status, response.getheaders(), data
    finally:
        connection.close()


def provider_self():
    # Export only shapes and comparisons with invented fixtures, never claims.
    token = worker.read("native.json")["tokens"]["admission"]
    status, _, body = native().request("/v1/self", bearer=token)
    value = json.loads(body) if status == 200 else None
    attrs = value.get("youare", {}).get("attrs", {}) if isinstance(value, dict) else {}
    members = attrs.get("memberof")
    uuid = attrs.get("uuid")
    uuid_pattern = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    evidence = {"status_200": status == 200, "root_object": isinstance(value, dict),
        "youare_attrs_object": isinstance(attrs, dict) and bool(attrs),
        "name_matches_requested_service": attrs.get("name") == ["synthetic_worker_admission"],
        "class_contains_service_account": "service_account" in attrs.get("class", []),
        "uuid_single_lowercase_uuid": isinstance(uuid, list) and len(uuid) == 1 and bool(re.fullmatch(uuid_pattern, uuid[0])),
        "memberof_present": members is not None, "memberof_string_array": isinstance(members, list) and all(isinstance(x, str) for x in members),
        "memberof_all_uuid": isinstance(members, list) and bool(members) and all(re.fullmatch(uuid_pattern, x) for x in members),
        "memberof_all_spn": isinstance(members, list) and bool(members) and all(re.fullmatch(r"[a-z0-9_]+@log\.mrj\.am", x) for x in members),
        "memberof_all_plain_names": isinstance(members, list) and bool(members) and all(re.fullmatch(r"[a-z0-9_]+", x) for x in members),
        "onboarding_name_or_spn_present": isinstance(members, list) and any(x in ("idm_people_on_boarding", "idm_people_on_boarding@log.mrj.am") for x in members)}
    Path("/run/native-self-shape.json").write_text(json.dumps(evidence, sort_keys=True))
    print(json.dumps(evidence, sort_keys=True))


def prepare():
    ROOT.mkdir(mode=0o700)
    client = native()
    admin = worker.read("native.json")["idm"]
    client.api("/v1/person", {"attrs": {"name": [PERSON], "displayname": ["Invented HTTP deletion"], "mail": [MAIL]}}, bearer=admin)
    subject = client.api("/v1/person/" + PERSON, bearer=admin)["attrs"]["uuid"][0]
    bearer = client.login(PERSON, client.recover(PERSON), False)
    sql("INSERT INTO vision_gestion.comptes(utilisateur,affichage) VALUES('" + USER + "','Invented HTTP deletion');"
        "INSERT INTO vision_gestion.identites(emetteur,sujet,utilisateur) VALUES('" + ISSUER + "','" + subject + "','" + USER + "');"
        "INSERT INTO vision_profils(utilisateur) VALUES('" + USER + "');"
        "INSERT INTO vision_fiches(utilisateur,titre,contenu,suivi) VALUES('" + USER + "','Invented private content','SYNTHETIC-DELETION-CONTENT','');")
    with sqlite3.connect(worker.BROKER) as db:
        db.execute("INSERT INTO log_principaux VALUES(?,?,?,?,?)", (subject, MAIL, 604800, "any", int(time.time())))
    save("native.json", {"subject": subject, "bearer": bearer})
    save("before.json", worker.snapshot(USER))
    save("survivor.json", worker.snapshot("synthetic_survivor"))


def login():
    status, headers, _ = http("/auth/connexion?retour=%2F", port=3002)
    require(status == 302, "DELETION_LOGIN_START")
    values = dict((key.lower(), value) for key, value in headers)
    redirect = native().authorize(urlsplit(values["location"]).query, read("native.json")["bearer"])
    status, headers, _ = http("/auth/retour?" + urlsplit(redirect).query, port=3002,
                              headers={"Cookie": values["set-cookie"].split(";", 1)[0]})
    require(status == 302, "DELETION_LOGIN_CALLBACK")
    cookies = [value.split(";", 1)[0] for key, value in headers if key.lower() == "set-cookie" and value.startswith("__Host-mrj_session=")]
    require(len(cookies) == 1, "DELETION_SESSION_MISSING")
    status, _, data = http("/auth/session", port=3002, headers={"Cookie": cookies[0]})
    require(status == 200, "DELETION_SESSION_METADATA")
    save("session.json", {"cookie": cookies[0], "csrf": json.loads(data)["csrf"]})


def headers():
    session = read("session.json")
    return {"Cookie": session["cookie"], "X-CSRF-Token": session["csrf"], "Origin": "https://vision.mrj.am"}


def no_effect():
    require(worker.snapshot(USER) == read("before.json"), "DELETION_EARLY_OR_WRONG_EFFECT")
    require(worker.snapshot("synthetic_survivor") == read("survivor.json"), "DELETION_OTHER_ACCOUNT_CHANGED")


def guards():
    route = "/api/web/effacer_compte"
    body = {"confirmation": "EFFACER VISION"}
    require(http(route, body)[0] == 401, "DELETION_WITHOUT_SESSION")
    for key, value in (("Origin", "https://audition.mrj.am"), ("X-CSRF-Token", "wrong")):
        require(http(route, body, headers=dict(headers(), **{key: value}))[0] == 403, "DELETION_BAD_ORIGIN_OR_CSRF")
    for changed in ({"confirmation": "NO"}, dict(body, utilisateur="synthetic_survivor")):
        require(http(route, changed, headers=headers())[0] == 400, "DELETION_BAD_CONFIRMATION_OR_OWNER")
    require(http(route, body, headers=dict(headers(), Host="audition.mrj.am"))[0] == 421, "DELETION_WRONG_HOST")
    no_effect()
    require(sql("SELECT count(*) FROM vision_effacements.demandes", "vision_journal") == "0", "REFUSED_REQUEST_CREATED_INTENTION")


def pending():
    for _ in range(2):
        status, _, data = http("/api/web/effacer_compte", {"confirmation": "EFFACER VISION"}, headers=headers())
        require(status == 202 and json.loads(data).get("effacement_en_attente") is True, "DELETION_NOT_DURABLY_PENDING")
    require(sql("SELECT count(*) FROM vision_effacements.demandes WHERE utilisateur='" + USER + "' AND archive_confirmee_a IS NULL", "vision_journal") == "1", "DELETION_INTENTION_NOT_UNIQUE")
    no_effect()


def archive_pending():
    with sqlite3.connect(worker.ARCHIVE) as db:
        rows = db.execute("SELECT message,etat FROM courriels").fetchall()
    require(len(rows) == 1 and rows[0][1] == "attente", "DELETION_ARCHIVE_NOT_PENDING")
    parsed = email.message_from_bytes(rows[0][0], policy=email.policy.default)
    encrypted = [part.get_payload(decode=True) for part in parsed.walk() if not part.is_multipart()
                 and (part.get_payload(decode=True) or b"").startswith(b"age-encryption.org/v1\n")]
    require(len(encrypted) == 1, "DELETION_ARCHIVE_NOT_ENCRYPTED")
    record = json.loads(command(["age", "--decrypt", "-i", "/etc/synthetic-age/key"], encrypted[0]))
    require(record.get("version") == 1 and record.get("utilisateur") == USER, "DELETION_ARCHIVE_WRONG_OWNER")
    pending()


def deleted():
    require(sql("SELECT (archive_confirmee_a IS NOT NULL AND archive_sha256 IS NOT NULL)::int FROM vision_effacements.demandes WHERE utilisateur='" + USER + "'", "vision_journal") == "1", "DELETION_ARCHIVE_RECEIPT_MISSING")
    status, _, data = http("/api/web/effacer_compte", {"confirmation": "EFFACER VISION"}, headers=headers())
    document = json.loads(data)
    require(status == 200 and document.get("efface") is True and document.get("identite_commune_conservee") is True
            and document.get("autres_outils_conserves") is True, "DELETION_HTTP_NOT_COMPLETE")
    check_deleted()
    require(http("/api/web/effacer_compte", {"confirmation": "EFFACER VISION"}, headers=headers())[0] == 403, "DELETED_ACCOUNT_STILL_AUTHORIZED")


def check_deleted():
    require(worker.snapshot(USER) == {"compte": None, "profil": None, "fiches": None}, "DELETION_CONTENT_RETAINED")
    require(worker.snapshot("synthetic_survivor") == read("survivor.json"), "DELETION_OTHER_ACCOUNT_CHANGED")
    subject = read("native.json")["subject"]
    require(native().api("/v1/person/" + subject, bearer=worker.read("native.json")["idm"])["attrs"]["uuid"] == [subject], "VISION_DELETION_REMOVED_COMMON_IDENTITY")


def replayed():
    check_deleted()
    require(sql("SELECT (applique_sha256=archive_sha256)::int FROM vision_effacements.demandes WHERE utilisateur='" + USER + "'", "vision_journal") == "1", "DELETION_REPLAY_RECEIPT_MISSING")


def readiness_limitation():
    status, _, data = http("/readyz")
    require(status == 200 and "vision-account-deletion" not in json.loads(data)["capabilities"], "FALSE_READY_CAPABILITY_CLAIM")
    result = subprocess.run([os.environ["SYNTHETIC_SERVER"], "check-config", os.environ["SYNTHETIC_REQUIRED_CONFIG"]], capture_output=True)
    require(result.returncode != 0 and result.stdout == b"" and json.loads(result.stderr) == {"code": "REQUIRED_CAPABILITY_MISSING"}, "HARD_CODED_READINESS_LIMIT_CHANGED")


def no_leak():
    data = command(["journalctl", "--no-pager", "-o", "cat", "-u", "mrjam-rust-blue", "-u", "mrjam-identity", "-u", "mrjam-vision-archive", "-u", "mrjam-vision-replay"])
    session = read("session.json")
    for value in (USER, MAIL, "SYNTHETIC-DELETION-CONTENT", session["cookie"], session["csrf"], read("native.json")["bearer"]):
        require(value.encode() not in data, "DELETION_PRIVATE_DIAGNOSTIC")


ACTIONS = {"provider-self": provider_self, "prepare": prepare, "login": login, "guards": guards,
           "pending": pending, "archive-pending": archive_pending, "deleted": deleted,
           "replayed": replayed, "readiness-limitation": readiness_limitation, "no-leak": no_leak}
if __name__ == "__main__":
    try:
        require(len(sys.argv) == 2 and sys.argv[1] in ACTIONS, "SYNTHETIC_DELETION_SCOPE")
        ACTIONS[sys.argv[1]]()
    except Exception as error:
        code = str(error) if isinstance(error, RuntimeError) and re.fullmatch(r"[A-Z0-9_]+", str(error)) else type(error).__name__
        print("SYNTHETIC_DELETION_TEST_FAILED:" + code, file=sys.stderr)
        raise SystemExit(1)
