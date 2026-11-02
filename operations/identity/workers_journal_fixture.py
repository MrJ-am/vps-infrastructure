#!/usr/bin/env python3
"""Closed invented journal adoption scenarios; imported only inside the test VM."""
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, "/etc")
from workers_fixture import ISSUER, ROOT, SECRET, private_file, read, require, save, sql

LEGACY = "https://log.mrj.am/realms/mrjam"
OLD = "synthetic_journal_legacy"
NATIVE = "99999999-9999-4999-8999-999999999999"


def snapshot():
    return json.loads(sql("SELECT jsonb_build_object('demandes',(SELECT coalesce(jsonb_agg(to_jsonb(d) ORDER BY utilisateur),'[]'::jsonb) "
        "FROM vision_effacements.demandes d),'fermetures',(SELECT coalesce(jsonb_agg(to_jsonb(f) ORDER BY sujet),'[]'::jsonb) "
        "FROM vision_effacements.fermetures f),'revision',(SELECT numero FROM vision_effacements.revision WHERE singleton))", "vision_journal"))


def closure(subject, issuer, date, user):
    return {"version": 2, "type": "fermeture_commune", "sujet": subject, "emetteur": issuer,
            "confirmee_a": date, "outils": {"vision": [user]}}


def source(name, records):
    private_file(SECRET / ("journal-" + name), "".join(json.dumps(value, sort_keys=True) + "\n" for value in records))


def prepare():
    now = int(time.time()) - 5
    save("journal-date.json", now)
    private_file(SECRET / "journal-sources", json.dumps(["lisp", "cycle", "fermeture"]))
    private_file(SECRET / "journal-configuration", json.dumps({"schema_version": 1, "journal_database": "vision_journal"}))
    source("lisp", [{"utilisateur": "synthetic_journal_cycle", "confirmee_a": now + 2208988800}])
    source("cycle", [{"utilisateur": "synthetic_journal_cycle", "confirmee_a": now - 1}])
    source("fermeture", [closure(OLD, LEGACY, now, "synthetic_import_old"), closure(NATIVE, ISSUER, now, "synthetic_import_native")])


def imported():
    now = read("journal-date.json")
    values = json.loads(sql("SELECT jsonb_agg(jsonb_build_object('sujet',sujet,'emetteur',emetteur,'comptes',comptes) ORDER BY sujet) "
        "FROM vision_effacements.fermetures WHERE sujet IN ('" + OLD + "','" + NATIVE + "')", "vision_journal"))
    require(values == [{"sujet": NATIVE, "emetteur": ISSUER, "comptes": ["synthetic_import_native"]},
                       {"sujet": OLD, "emetteur": LEGACY, "comptes": ["synthetic_import_old"]}], "JOURNAL_ADOPTION_CHANGED_ISSUER_OR_SCOPE")
    require(sql("SELECT extract(epoch FROM demande_a)::bigint FROM vision_effacements.demandes WHERE utilisateur='synthetic_journal_cycle'", "vision_journal")
            == str(now - 1), "JOURNAL_EPOCH_OR_EARLIEST_DATE")
    require(sql("SELECT count(*) FROM vision_effacements.demandes WHERE utilisateur LIKE 'synthetic_import_%'", "vision_journal") == "2", "JOURNAL_LOST_CONTENT_INTENTIONS")
    if not (ROOT / "journal-before-repeat.json").exists():
        sql("UPDATE vision_effacements.fermetures SET archive_confirmee_a=now(),archive_sha256=repeat('f',64) WHERE sujet IN ('" + OLD + "','" + NATIVE + "')", "vision_journal")
        value = snapshot()
        value.pop("revision")
        save("journal-before-repeat.json", value)
    else:
        value = snapshot()
        value.pop("revision")
        require(value == read("journal-before-repeat.json"), "JOURNAL_REPEAT_CHANGED_EVENTS_OR_RECEIPTS")


def collision():
    now = read("journal-date.json")
    save("journal-before-negative.json", snapshot())
    source("fermeture", [closure(NATIVE, LEGACY, now, "synthetic_import_native")])


def ambiguous():
    save("journal-before-negative.json", snapshot())
    private_file(SECRET / "journal-sources", '["cycle","cycle"]')


def refused():
    require(snapshot() == read("journal-before-negative.json"), "JOURNAL_REFUSAL_WROTE_PARTIAL_DATA")


ACTIONS = {"prepare": prepare, "imported": imported, "collision": collision, "ambiguous": ambiguous, "refused": refused}
if __name__ == "__main__":
    try:
        require(len(sys.argv) == 2 and sys.argv[1] in ACTIONS, "SYNTHETIC_JOURNAL_SCOPE")
        ACTIONS[sys.argv[1]]()
    except Exception as error:
        code = str(error) if isinstance(error, RuntimeError) and re.fullmatch(r"[A-Z0-9_]+", str(error)) else type(error).__name__
        print("SYNTHETIC_JOURNAL_TEST_FAILED:" + code, file=sys.stderr)
        raise SystemExit(1)
