#!/usr/bin/env python3
"""Synthetic VM only: real native provider, production worker protocols, closed verdicts."""
import base64
import email
import email.policy
import hashlib
from http.client import HTTPConnection
import json
import os
from pathlib import Path
import re
import socket
import socketserver
import sqlite3
import subprocess
import sys
import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, "/etc/identity-native-fixture")
from qualify import Native
from fixture import ISSUER
sys.path.insert(0, "/etc/native-adoption")
import adopt

ROOT = Path("/var/lib/synthetic-workers")
STATE = Path("/var/lib/mrjam-vision-admission/admissions.sqlite")
BROKER = Path("/var/lib/mrjam-metier/log/sessions.sqlite")
CYCLE = Path("/var/lib/mrjam-vision-cycle/courriels.sqlite")
ARCHIVE = Path("/var/lib/mrjam-vision-archive/courriels.sqlite")
SECRET = Path("/var/lib/synthetic-worker-credentials")
OLD_ID = "11111111-2222-4333-8444-555555555555"
MAIL = "adult@synthetic.invalid"
SENDER = "sender@synthetic.invalid"
INVITATION = "A" * 43
CLOSURE = "SyntheticClosureOnly1234567890123456789"
APPROVAL = "SyntheticApprovalOnly1234567890123456789"
SMTP_PASSWORD = "SyntheticSMTPOnly1234567890"


def require(value, code):
    if not value:
        raise RuntimeError(code)


def command(argv, data=None, timeout=45):
    result = subprocess.run(argv, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    require(result.returncode == 0, "SYNTHETIC_COMMAND_FAILED")
    return result.stdout


def sql(statement, database="vision"):
    return command(["runuser", "-u", "postgres", "--", "psql", "-X", "-w", "-qAt",
                    "-h", "/run/postgresql", "-d", database, "-v", "ON_ERROR_STOP=1"],
                   statement.encode(), 120).decode().strip()


def save(name, value):
    path = ROOT / name
    path.write_text(json.dumps(value, sort_keys=True))
    path.chmod(0o600)


def read(name):
    return json.loads((ROOT / name).read_text())


def native():
    value = object.__new__(Native)
    value.package = Path(os.environ["SYNTHETIC_KANIDM_PACKAGE"])
    value.config = Path("/etc/kanidm/server.toml")
    value.crypto = SimpleNamespace(ca=Path("/etc/synthetic-identity-tls/ca.pem"))
    value.port = 8443
    return value


def recover(client, name):
    require(name in ("admin", "idm_admin"), "SYNTHETIC_ADMIN_SCOPE")
    value = json.loads(command([str(client.package / "bin/kanidmd"), "-c", str(client.config),
                               "scripting", "recover-account", name]))
    require(value.get("status") == "ok", "SYNTHETIC_RECOVERY_FAILED")
    return value["output"]


def private_file(path, value, gid=0, mode=0o400):
    path.write_bytes(value if isinstance(value, bytes) else value.encode())
    os.chown(path, 0, gid)
    path.chmod(mode)


def prepare_sql():
    require(os.getuid() == 0 and not ROOT.exists(), "SYNTHETIC_SCOPE")
    ROOT.mkdir(mode=0o700)
    SECRET.mkdir(mode=0o700)
    command(["runuser", "-u", "postgres", "--", "createdb", "vision"])
    command(["runuser", "-u", "postgres", "--", "createdb", "vision_journal"])
    sql("CREATE EXTENSION vector;")
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
        + ",".join("vision_journal_" + name for name in names) + ";", "vision_journal")
    sql("UPDATE vision_gestion.configuration SET inscriptions_ouvertes=true,notice_version='synthetic-native-v1',"
        "responsable='Invented operator',contact='operator@synthetic.invalid',pays_hebergement='Synthetic';"
        "INSERT INTO vision_gestion.invitations(condensat,intitule,maximum,quota_octets,expire_a) VALUES('"
        + hashlib.sha256(INVITATION.encode()).hexdigest()
        + "','Invented invitation',10,10000,now()+interval '1 day');"
        "INSERT INTO vision_gestion.comptes(utilisateur,affichage,administrateur) VALUES"
        "('synthetic_admin','Invented admin',true),('synthetic_survivor','Invented survivor',false),"
        "('synthetic_cycle','Invented cycle',false);"
        "INSERT INTO vision_profils(utilisateur) VALUES('synthetic_survivor'),('synthetic_cycle');"
        "INSERT INTO vision_fiches(utilisateur,titre,contenu,suivi) VALUES"
        "('synthetic_survivor','Invented survivor','No real data',''),('synthetic_cycle','Invented cycle','No real data','');")
    BROKER.parent.mkdir(parents=True, mode=0o700)
    for directory in (BROKER.parent.parent, BROKER.parent):
        directory.chmod(0o700)
        os.chown(directory, 984, 984)
    with sqlite3.connect(BROKER) as db:
        db.executescript(Path("/etc/identity-native-fixture/legacy-state.sql").read_text())
    BROKER.chmod(0o600)
    os.chown(BROKER, 984, 984)
    private_file(SECRET / "smtp.json", json.dumps({"host": "smtp.protonmail.ch", "port": 587,
        "username": SENDER, "password": SMTP_PASSWORD, "from_address": SENDER,
        "starttls_required": True, "certificate_verification": True}))
    private_file(SECRET / "closure", CLOSURE)
    private_file(SECRET / "approval", APPROVAL)
    private_file(SECRET / "archive-recipient", "archive@synthetic.invalid")
    save("survivor.json", snapshot("synthetic_survivor"))


def prepare_adoption():
    parent = Path("/var/lib/mrjam-admission-adoption-input")
    parent.mkdir(mode=0o700, exist_ok=True)
    request = adopt.reference(native=True, with_enrolment=True)
    queue = adopt.reference(mail=True, native=True, with_hash=True, with_business_hash=True)
    now = int(time.time())
    request.execute("INSERT INTO demandes VALUES(" + ",".join("?" for _ in range(25)) + ")", (
        OLD_ID, "a" * 64, "synthetic-native-v1", "retained@synthetic.invalid", "France", "majeur", "",
        "Invented retained", 0, 0, None, None, now - 30, None, None, None, None, None,
        "22222222-2222-4222-8222-222222222222", 1, "admise", now - 60, now + 3600, now - 10,
        "https://log.mrj.am/ui/reset?token=synthetic-retained-invitation"))
    # A previously accepted retained message may have an empty body. Neither
    # proof may be converted into the other implementation's semantic digest.
    queue.execute("INSERT INTO courriels VALUES(?,?,?,?,?,?,?,?,?,?)", (
        "enrol:" + OLD_ID, b"", now - 20, "accepte_relais", 2, now + 600, now - 10, None,
        "b" * 64, "c" * 64))
    request.commit(); queue.commit()
    for name, db in (("requests.sqlite", request), ("mail.sqlite", queue)):
        private_file(parent / name, db.serialize(), gid=947, mode=0o440)
        db.close()
    save("adoption-source.json", {name: hashlib.sha256((parent / name).read_bytes()).hexdigest()
                                  for name in ("requests.sqlite", "mail.sqlite")})


def check_adoption():
    before = read("adoption-source.json")
    require(all(hashlib.sha256((Path("/var/lib/mrjam-admission-adoption-input") / key).read_bytes()).hexdigest() == value
                for key, value in before.items()), "ADOPTION_CHANGED_SOURCE")
    with sqlite3.connect(STATE) as db:
        require(db.execute("SELECT enrolement,etat FROM demandes WHERE id=?", (OLD_ID,)).fetchone()
                == ("https://log.mrj.am/ui/reset?token=synthetic-retained-invitation", "admise"), "ADOPTION_LOST_ENROLMENT")
        require(db.execute("SELECT message,empreinte,contenu_sha256,empreinte_metier,essais FROM courriels WHERE cle=?",
                           ("enrol:" + OLD_ID,)).fetchone() == (b"", "b" * 64, None, "c" * 64, 2), "ADOPTION_CHANGED_OPAQUE_PROOFS")
    item = STATE.stat()
    require(item.st_uid == item.st_gid == 947 and item.st_mode & 0o777 == 0o600, "ADOPTION_OWNER")


def prepare_native():
    client = native()
    admin = client.login("admin", recover(client, "admin"), True)
    idm = client.login("idm_admin", recover(client, "idm_admin"), True)
    for user in ("synthetic_cycle", "synthetic_survivor"):
        client.api("/v1/person", {"attrs": {"name": [user], "displayname": ["Invented person"],
                                           "mail": [user + "@synthetic.invalid"]}}, bearer=idm)
        subject = client.api("/v1/person/" + user, bearer=idm)["attrs"]["uuid"][0]
        sql("INSERT INTO vision_gestion.identites(emetteur,sujet,utilisateur) VALUES('" + ISSUER + "','" + subject + "','" + user + "');")
        save(user + ".json", {"subject": subject})
    tokens = {}
    for capability, groups in (("admission", ["idm_people_on_boarding", "idm_account_mail_read"]),
                               ("cycle", ["idm_account_mail_read"]),
                               ("replay", ["idm_people_admins", "idm_account_mail_read"])):
        name = "synthetic_worker_" + capability
        client.api("/v1/service_account", {"attrs": {"name": [name], "displayname": ["Invented worker"],
                                                    "entry_managed_by": ["idm_admin"]}}, bearer=idm)
        for group in groups:
            client.api("/v1/group/" + group + "/_attr/member", [name],
                       bearer=admin if group == "idm_account_mail_read" else idm)
        token = client.api("/v1/service_account/" + name + "/_api_token",
                           {"label": "synthetic-only", "expiry": int(time.time()) + 3600, "read_write": True}, bearer=idm)
        require(isinstance(token, str), "NATIVE_SERVICE_TOKEN_SHAPE")
        tokens[capability] = token
        private_file(SECRET / (capability + ".token"), token)
    client.api("/v1/oauth2/_basic", {"attrs": {"name": ["mrjam-vision"], "displayname": ["Invented broker"],
        "oauth2_rs_origin_landing": ["https://vision.mrj.am/"], "oauth2_strict_redirect_uri": ["true"]}}, bearer=idm)
    client.api("/v1/oauth2/mrjam-vision/_attr/oauth2_rs_origin", ["https://vision.mrj.am/auth/retour"], bearer=idm)
    client.api("/v1/oauth2/mrjam-vision/_scopemap/idm_all_persons", ["openid", "profile", "email"], bearer=idm)
    secret = client.api("/v1/oauth2/mrjam-vision/_basic_secret", bearer=idm)
    path = Path("/var/lib/mrjam-identite")
    path.mkdir(mode=0o700)
    private_file(path / "kanidm-vision.secret", secret)
    save("native.json", {"admin": admin, "idm": idm, "tokens": tokens, "secret": secret})


def http(path, body=None, *, port=3027, bearer=None, origin=None, raw=None):
    connection = HTTPConnection("127.0.0.1", port, timeout=15)
    headers = {"Host": "mrjam-fermeture.internal" if port == 3028 else "mrjam-admission.internal", "Connection": "close"}
    if bearer:
        headers["Authorization"] = "Bearer " + bearer
    if origin:
        headers["Origin"] = origin
    wire = raw if raw is not None else json.dumps(body).encode() if body is not None else None
    if wire is not None:
        headers["Content-Type"] = "application/json"
    try:
        connection.request("POST" if wire is not None else "GET", path, wire, headers)
        response = connection.getresponse()
        data = response.read(16385)
        require(len(data) <= 16384, "WORKER_RESPONSE_BOUND")
        return response.status, json.loads(data) if data else None
    finally:
        connection.close()


def readiness():
    require(http("/interne/disponibilite", bearer=APPROVAL) == (200, {"disponible": True}), "WORKER_LOCAL_NOT_READY")


def capabilities():
    client = native()
    document = read("native.json")
    subject = read("synthetic_survivor.json")["subject"]
    expected = client.api("/v1/person/" + subject, bearer=document["idm"])
    for name in ("admission", "cycle"):
        status, _, _ = client.request("/v1/person/" + subject, method="DELETE", bearer=document["tokens"][name])
        require(status == 403, "READ_OR_ONBOARDING_TOKEN_CAN_DELETE")
    profile = client.api("/v1/person/" + subject, bearer=document["tokens"]["cycle"])
    require(profile["attrs"]["mail"] == ["synthetic_survivor@synthetic.invalid"], "CYCLE_TOKEN_CANNOT_READ_MAIL")
    require(client.api("/v1/person/" + subject, bearer=document["idm"]) == expected, "CAPABILITY_REFUSAL_CHANGED_PERSON")


def new_request():
    return {"invitation": INVITATION, "notice": "synthetic-native-v1", "courriel": MAIL,
            "pays": "France", "age": "majeur", "parent": "", "pseudonyme": "Invented adult"}


def closed():
    require(http("/auth/admission", new_request(), origin="https://vision.mrj.am")[0] >= 400, "CLOSED_ADMISSION_ACCEPTED")


def request_admission():
    for _ in range(2):
        require(http("/auth/admission", new_request(), origin="https://vision.mrj.am")[0] == 202, "ADMISSION_REQUEST_FAILED")
    with sqlite3.connect(STATE) as db:
        rows = db.execute("SELECT id,sujet FROM demandes WHERE courriel=?", (MAIL,)).fetchall()
        require(len(rows) == 1 and rows[0][1] is None, "ADMISSION_DUPLICATED_OR_EARLY_PERSON")
        identifier = rows[0][0]
        message = db.execute("SELECT message FROM courriels WHERE cle=?", ("admission:" + identifier,)).fetchone()[0]
    parsed = email.message_from_bytes(message, policy=email.policy.default)
    require(str(parsed["To"]) == MAIL and str(parsed["From"]) == SENDER, "CONFIRMATION_MAIL_SCOPE")
    body = parsed.get_payload(decode=True).decode()
    token = re.search(r"https://vision\.mrj\.am/admission#([A-Za-z0-9_-]{43})", body).group(1)
    require(not any(row["attrs"].get("mail") == [MAIL] for row in native().api("/v1/person", bearer=read("native.json")["idm"])), "PERSON_BEFORE_CONFIRMATION")
    for bad_path, raw, origin in (("/auth/admission?x=1", json.dumps(new_request()).encode(), "https://vision.mrj.am"),
                                  ("/auth/admission", b'{"age":"majeur","age":"majeur"}', "https://vision.mrj.am"),
                                  ("/auth/admission", json.dumps(new_request()).encode(), "https://wrong.invalid")):
        require(http(bad_path, raw=raw, origin=origin)[0] >= 400, "AMBIGUOUS_ADMISSION_ACCEPTED")
    require(http("/auth/admission/confirmer", {"token": token, "acceptation": True}, origin="https://vision.mrj.am")[0] == 200, "CONFIRMATION_FAILED")
    require(http("/auth/admission/confirmer", {"token": token, "acceptation": True}, origin="https://vision.mrj.am")[0] >= 400, "CONFIRMATION_REPLAY")
    save("admission.json", {"id": identifier})


def partial():
    identifier = read("admission.json")["id"]
    with sqlite3.connect(STATE) as db:
        row = db.execute("SELECT sujet,etat,enrolement FROM demandes WHERE id=?", (identifier,)).fetchone()
        require(row and row[0] and row[1] in ("reservation", "provisionnee", "attente") and row[2] is None, "NO_DURABLE_PARTIAL_ADMISSION")
    subject = row[0]
    require(re.fullmatch(r"[0-9a-f-]{36}", subject), "NATIVE_UUID_MISSING")
    attrs = native().api("/v1/person/" + subject, bearer=read("native.json")["idm"])["attrs"]
    require(attrs.get("mail") == [MAIL], "NATIVE_MAIL_WRONG")
    require(sql("SELECT count(*) FROM vision_gestion.identites WHERE emetteur='" + ISSUER + "' AND sujet='" + subject + "'") == "1", "NATIVE_SQL_MAPPING_MISSING")
    save("partial.json", {"subject": subject})


def completed():
    identifier = read("admission.json")["id"]
    subject = read("partial.json")["subject"]
    with sqlite3.connect(STATE) as db:
        row = db.execute("SELECT sujet,etat,enrolement FROM demandes WHERE id=?", (identifier,)).fetchone()
        require(row and row[0] == subject and row[1] == "admise" and row[2], "ADMISSION_NOT_COMPLETED")
        messages = db.execute("SELECT cle,message,empreinte,contenu_sha256,empreinte_metier FROM courriels WHERE cle IN (?,?) ORDER BY cle",
                              ("enrol:" + identifier, "admis:" + identifier)).fetchall()
    require(len(messages) == 2, "NATIVE_MAIL_PAIR_MISSING")
    for key, message, *_ in messages:
        parsed = email.message_from_bytes(message, policy=email.policy.default)
        require(str(parsed["To"]) == MAIL and str(parsed["From"]) == SENDER, "NATIVE_MAIL_RECIPIENT")
        require(parsed["Message-ID"], "DURABLE_MESSAGE_ID_MISSING")
        if key.startswith("enrol:"):
            require(row[2] in parsed.get_payload(decode=True).decode(), "ENROLMENT_NOT_IN_MESSAGE")
    with sqlite3.connect(BROKER) as db:
        require(db.execute("SELECT mail FROM log_principaux WHERE subject=?", (subject,)).fetchone() == (MAIL,), "BROKER_REGISTRATION_MISSING")
    require(sql("SELECT utilise FROM vision_gestion.invitations WHERE condensat='" + hashlib.sha256(INVITATION.encode()).hexdigest() + "'") == "1", "INVITATION_CONSUMED_TWICE")
    people = native().api("/v1/person", bearer=read("native.json")["idm"])
    require(sum(row["attrs"].get("mail") == [MAIL] for row in people) == 1, "NATIVE_PERSON_DUPLICATED")
    snapshot_value = {"subject": subject, "url": row[2], "messages": [[key, base64.b64encode(m).decode(), a, b, c] for key, m, a, b, c in messages]}
    if (ROOT / "completed.json").exists():
        require(read("completed.json") == snapshot_value, "RESTART_REISSUED_ENROLMENT_OR_MESSAGE")
    else:
        save("completed.json", snapshot_value)


def enrolment():
    document = read("completed.json")
    token = parse_qs(urlsplit(document["url"]).query, strict_parsing=True)["token"][0]
    status, _, body = native().request("/v1/credential/_exchange_intent", token)
    require(status == 200 and isinstance(json.loads(body), list), "NATIVE_ENROLMENT_NOT_REDEEMABLE")


def snapshot(user):
    require(user in ("synthetic_cycle", "synthetic_survivor") or re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", user), "SYNTHETIC_USER_SHAPE")
    return json.loads(sql("SELECT jsonb_build_object('compte',(SELECT to_jsonb(c) FROM vision_gestion.comptes c WHERE utilisateur='" + user
        + "'),'profil',(SELECT to_jsonb(p) FROM vision_profils p WHERE utilisateur='" + user
        + "'),'fiches',(SELECT jsonb_agg(to_jsonb(f) ORDER BY id) FROM vision_fiches f WHERE utilisateur='" + user + "'))"))


def cycle_begin():
    result = json.loads(sql("SELECT vision_gestion.administrer('synthetic_admin','demander_suppression',jsonb_build_object('utilisateur','synthetic_cycle','version',(SELECT version FROM vision_gestion.comptes WHERE utilisateur='synthetic_cycle')))"))
    require(isinstance(result.get("suppression", {}).get("id"), str), "CYCLE_NOTICE_NOT_CREATED")
    save("cycle-notice.json", {"id": result["suppression"]["id"]})


def cycle_pending():
    with sqlite3.connect(CYCLE) as db:
        rows = db.execute("SELECT message,etat,essais FROM courriels").fetchall()
    require(len(rows) == 1 and rows[0][1] == "attente" and rows[0][2] > 0, "SMTP_REFUSAL_NOT_DURABLE")
    parsed = email.message_from_bytes(rows[0][0], policy=email.policy.default)
    require(str(parsed["To"]) == "synthetic_cycle@synthetic.invalid", "CYCLE_NATIVE_MAIL_WRONG")
    require(sql("SELECT (envoye_a IS NULL AND echeance_a IS NULL)::int FROM vision_gestion.preavis WHERE utilisateur='synthetic_cycle'") == "1", "SMTP_FAILURE_STARTED_DEADLINE")
    save("cycle-message.json", {"sha256": hashlib.sha256(rows[0][0]).hexdigest()})


def cycle_receipt():
    # Explicit fixture receipt, not an SMTP-delivery claim.
    with sqlite3.connect(CYCLE) as db:
        db.execute("UPDATE courriels SET etat='accepte_relais',accepte=?,erreur=NULL", (int(time.time()),))


def cycle_due():
    require(sql("SELECT (echeance_a=envoye_a+interval '30 days' AND echeance_a>now())::int FROM vision_gestion.preavis WHERE utilisateur='synthetic_cycle'") == "1", "CYCLE_DEADLINE_WRONG")
    sql("UPDATE vision_gestion.preavis SET envoye_a=now()-interval '31 days',echeance_a=now()-interval '1 day' WHERE utilisateur='synthetic_cycle'")


def cycle_archive_pending():
    require(snapshot("synthetic_cycle")["compte"] is not None, "CYCLE_ERASED_WITHOUT_ARCHIVE")
    require(sql("SELECT (archive_confirmee_a IS NULL)::int FROM vision_effacements.demandes WHERE utilisateur='synthetic_cycle'", "vision_journal") == "1", "CYCLE_ARCHIVE_NOT_PENDING")


def cycle_archive_receipt():
    # A synthetic SMTP receipt is injected into the outbox; the real archive
    # worker must still bind the message to its SQL intention itself.
    with sqlite3.connect(ARCHIVE) as db:
        db.execute("UPDATE courriels SET etat='accepte_relais',accepte=?,erreur=NULL", (int(time.time()),))


def cycle_erased():
    require(snapshot("synthetic_cycle") == {"compte": None, "profil": None, "fiches": None}, "CYCLE_CONTENT_RETAINED")
    require(snapshot("synthetic_survivor") == read("survivor.json"), "CYCLE_CHANGED_OTHER_ACCOUNT")


def closure_request():
    subject = read("partial.json")["subject"]
    body = {"emetteur": ISSUER, "sujet": subject, "confirmation": "FERMER MON COMPTE"}
    for wrong in (dict(body, emetteur="https://log.mrj.am/realms/mrjam"), dict(body, confirmation="NO")):
        require(http("/fermer", wrong, port=3028, bearer=CLOSURE)[0] >= 400, "CLOSURE_BAD_CONSENT_OR_ISSUER")
    require(http("/fermer", body, port=3028, bearer=APPROVAL)[0] >= 400, "CLOSURE_WRONG_CAPABILITY")
    status, response = http("/fermer", body, port=3028, bearer=CLOSURE)
    require(status == 202, "CLOSURE_HTTP_" + str(status))
    require(response.get("effacement_en_attente") is True, "CLOSURE_WITHOUT_ARCHIVE")
    accounts = json.loads(sql("SELECT comptes FROM vision_effacements.fermetures WHERE sujet='" + subject + "'", "vision_journal"))
    require(len(accounts) == 1 and snapshot(accounts[0])["compte"] is not None, "CLOSURE_EARLY_ERASURE")
    save("closure.json", {"subject": subject, "accounts": accounts})
    # Explicit test clock shift permits normal replay without sleeping 120s.
    sql("UPDATE vision_effacements.fermetures SET demande_a=now()-interval '121 seconds' WHERE sujet='" + subject + "'", "vision_journal")


def closure_archive_receipt():
    cycle_archive_receipt()


def archive_pending():
    with sqlite3.connect(ARCHIVE) as db:
        rows = db.execute("SELECT message,etat FROM courriels ORDER BY cle").fetchall()
    require(rows, "ARCHIVE_NOT_QUEUED")
    native_closure = read("closure.json") if (ROOT / "closure.json").exists() else None
    native_seen = False
    for message, state in rows:
        parsed = email.message_from_bytes(message, policy=email.policy.default)
        require(str(parsed["To"]) == "archive@synthetic.invalid", "ARCHIVE_RECIPIENT")
        pieces = [part.get_payload(decode=True) for part in parsed.walk()
                  if not part.is_multipart() and (part.get_payload(decode=True) or b"").startswith(b"age-encryption.org/v1\n")]
        require(len(pieces) == 1, "ARCHIVE_NOT_ENCRYPTED_AGE")
        record = json.loads(command(["age", "--decrypt", "-i", "/etc/synthetic-age/key"], pieces[0]))
        if record.get("type") == "fermeture_commune":
            require(native_closure and record.get("emetteur") == ISSUER and record.get("sujet") == native_closure["subject"]
                    and record.get("outils") == {"vision": native_closure["accounts"]}, "ARCHIVE_NATIVE_ISSUER_OR_SCOPE")
            require(state == "attente", "SMTP_REFUSAL_ACKNOWLEDGED_NATIVE_ARCHIVE")
            native_seen = True
        else:
            require(record.get("version") == 1 and record.get("utilisateur") == "synthetic_cycle", "ARCHIVE_CYCLE_SCOPE")
    if native_closure:
        require(native_seen, "ARCHIVE_NATIVE_RECORD_MISSING")
        require(sql("SELECT (archive_confirmee_a IS NULL)::int FROM vision_effacements.fermetures WHERE sujet='"
                    + native_closure["subject"] + "'", "vision_journal") == "1", "SMTP_REFUSAL_ACKNOWLEDGED_SQL")


def closure_partial():
    document = read("closure.json")
    status, _ = http("/fermer", {"emetteur": ISSUER, "sujet": document["subject"], "confirmation": "FERMER MON COMPTE"}, port=3028, bearer=CLOSURE)
    require(status >= 400, "MISSING_PURGE_REPORTED_COMPLETE")
    require(snapshot(document["accounts"][0])["compte"] is None, "CLOSURE_NOT_PARTIALLY_ERASED")


def closure_erased():
    document = read("closure.json")
    require(snapshot(document["accounts"][0]) == {"compte": None, "profil": None, "fiches": None}, "CLOSURE_CONTENT_RETAINED")
    with sqlite3.connect(STATE) as db:
        require(db.execute("SELECT count(*) FROM demandes WHERE courriel=?", (MAIL,)).fetchone() == (0,), "PURGE_REQUEST_RETAINED")
        require(db.execute("SELECT count(*) FROM courriels WHERE cle LIKE ?", ("%:" + read("admission.json")["id"],)).fetchone() == (0,), "PURGE_ENROLMENT_RETAINED")
    # Kanidm1.11.2 returns Json<Option<ProtoEntry>> (200/null), not only404:
    # primary server/core/src/https/v1.rs::person_id_get and client/person.rs.
    status, _, body = native().request("/v1/person/" + document["subject"], bearer=read("native.json")["idm"])
    require(status == 404 or (status == 200 and json.loads(body) is None), "REPLAY_NATIVE_PERSON_RETAINED")
    people = native().api("/v1/person", bearer=read("native.json")["idm"])
    require(not any(row["attrs"].get("uuid") == [document["subject"]] for row in people), "REPLAY_PERSON_STILL_LISTED")
    require(sql("SELECT (applique_sha256=archive_sha256)::int FROM vision_effacements.fermetures WHERE sujet='"
                + document["subject"] + "'", "vision_journal") == "1", "REPLAY_NOT_ACKNOWLEDGED")
    require(snapshot("synthetic_survivor") == read("survivor.json"), "CLOSURE_CHANGED_OTHER_ACCOUNT")


def no_secret_journal():
    data = command(["journalctl", "--no-pager", "-o", "cat", "-u", "mrjam-vision-admission", "-u", "mrjam-vision-cycle",
                    "-u", "mrjam-vision-closure", "-u", "mrjam-vision-replay", "-u", "mrjam-admission-adoption", "-u", "vision-journal-adoption"])
    private = read("native.json")
    markers = [CLOSURE, APPROVAL, SMTP_PASSWORD, MAIL, private["admin"], private["idm"], private["secret"],
               *private["tokens"].values(), read("partial.json")["subject"], read("completed.json")["url"],
               "synthetic_journal_legacy", "99999999-9999-4999-8999-999999999999"]
    require(not any(marker.encode() in data for marker in markers), "WORKER_PRIVATE_DIAGNOSTIC")


class RefusingSMTP(socketserver.StreamRequestHandler):
    def handle(self):
        self.request.settimeout(8)
        self.wfile.write(b"220 synthetic.invalid\r\n")
        line = self.rfile.readline(1025)
        require(line == b"EHLO mrj.am\r\n", "SMTP_UNEXPECTED_CLEAR_BYTES")
        self.wfile.write(b"250 AUTH PLAIN\r\n")
        require(self.rfile.readline(1025) == b"", "SMTP_PLAINTEXT_CREDENTIAL")


def smtp_refuse():
    class Server(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
    with Server(("127.0.0.1", 587), RefusingSMTP) as server:
        server.serve_forever()


ACTIONS = {name.replace("_", "-"): value for name, value in list(globals().items())
           if name in ("prepare_sql", "prepare_adoption", "check_adoption", "prepare_native", "capabilities", "readiness", "closed",
                       "request_admission", "partial", "completed", "enrolment", "cycle_begin", "cycle_pending", "cycle_receipt",
                       "cycle_due", "cycle_archive_pending", "cycle_archive_receipt", "cycle_erased", "closure_request",
                       "closure_archive_receipt", "closure_partial", "closure_erased", "archive_pending", "no_secret_journal", "smtp_refuse")}
if __name__ == "__main__":
    try:
        require(len(sys.argv) == 2 and sys.argv[1] in ACTIONS, "SYNTHETIC_ACTION_SCOPE")
        ACTIONS[sys.argv[1]]()
    except Exception as error:
        # All source/API/SQLite values stay inside the disposable VM.
        code = str(error) if isinstance(error, RuntimeError) and re.fullmatch(r"[A-Z0-9_]+", str(error)) else type(error).__name__
        print("SYNTHETIC_WORKER_TEST_FAILED:" + code, file=sys.stderr)
        raise SystemExit(1)
