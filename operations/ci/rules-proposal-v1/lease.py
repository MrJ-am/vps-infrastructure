"""One short-lived repository-bound lease; secret stays inside this process.

Reuses the qualified technical bootstrap's lock, configuration/running checks,
bounded CLI/SQL subprocess and private metadata reader. The older package and
its journal are never rewritten. No arbitrary SQL, account or repository input.
"""
from contextlib import contextmanager
import json
import os
import re
import stat

SCOPES = "read:user,write:repository"
LABEL = re.compile(r"mrjam-rules-proposal-[0-9a-f]{32}\Z")
JOURNAL = "rules-proposal-lease.json"
ACCOUNT = "mrjam-governance-bootstrap"
SELECT_TOKEN = """SELECT t.id FROM public.access_token t
JOIN public.\"user\" u ON u.id=t.uid
WHERE u.lower_name='mrjam-governance-bootstrap' AND t.name=:'lease'"""
SELECT_REPO = """SELECT r.id FROM public.repository r JOIN public.\"user\" u ON u.id=r.owner_id
WHERE u.lower_name='mrj-am' AND u.name='MrJ-am' AND u.type=1
AND r.lower_name='mrjam-validation' AND r.name='mrjam-validation'
AND r.is_private AND NOT r.is_empty AND NOT r.is_archived AND NOT r.is_mirror"""
COUNT = "BEGIN READ ONLY; SET LOCAL statement_timeout='3s'; SET LOCAL search_path=pg_catalog; SELECT count(*) FROM (" + SELECT_TOKEN + ") q; COMMIT;"
RESTRICT = """BEGIN; SET LOCAL statement_timeout='3s'; SET LOCAL lock_timeout='2s'; SET LOCAL search_path=pg_catalog;
SELECT 1 / ((SELECT count(*)=1 FROM (TOKEN) q) AND
 (SELECT count(*)=1 FROM (REPO) r) AND
 (SELECT count(*)=1 FROM public.access_token WHERE id IN (TOKEN)
   AND resource_all_repos AND string_to_array(scope,',') @> ARRAY['read:user','write:repository']
   AND cardinality(string_to_array(scope,','))=2) AND
 NOT EXISTS(SELECT FROM public.access_token_resource_repo WHERE token_id IN (TOKEN)))::int;
INSERT INTO public.access_token_resource_repo(token_id,repo_id,created_unix)
 SELECT t.id,r.id,extract(epoch FROM clock_timestamp())::bigint FROM (TOKEN) t CROSS JOIN (REPO) r;
UPDATE public.access_token SET resource_all_repos=false WHERE id IN (TOKEN);
SELECT 1 / ((SELECT count(*)=1 FROM public.access_token_resource_repo WHERE token_id IN (TOKEN)
 AND repo_id IN (REPO)) AND (SELECT count(*)=1 FROM public.access_token
 WHERE id IN (TOKEN) AND NOT resource_all_repos))::int;
COMMIT;""".replace("TOKEN", SELECT_TOKEN).replace("REPO", SELECT_REPO)
REVOKE = """BEGIN; SET LOCAL statement_timeout='3s'; SET LOCAL lock_timeout='2s'; SET LOCAL search_path=pg_catalog;
DELETE FROM public.access_token_resource_repo WHERE token_id IN (TOKEN);
DELETE FROM public.access_token WHERE id IN (TOKEN);
SELECT count(*) FROM (TOKEN) q; COMMIT;""".replace("TOKEN", SELECT_TOKEN)


class Refused(RuntimeError):
    pass


def require(value, code):
    if not value:
        raise Refused(code)


def sql(bootstrap, operation, label):
    require(type(label) is str and LABEL.fullmatch(label), "LEASE_LABEL_REFUSED")
    require(operation in ("count", "restrict", "revoke"), "LEASE_OPERATION_REFUSED")
    result = bootstrap.command([bootstrap.PSQL, "-X", "-w", "-qAt", "-h", "/run/postgresql",
        "-d", "forgejo", "-v", "ON_ERROR_STOP=1", "-v", "lease="+label],
        {"count":COUNT,"restrict":RESTRICT,"revoke":REVOKE}[operation].encode())
    require(result in (b"0\n", b"1\n") if operation == "count" else
            result == (b"1\n1\n" if operation == "restrict" else b"0\n"), "LEASE_SQL_RESULT_REFUSED")
    return int(result.strip()) if operation == "count" else None


def publish(bootstrap, label):
    target = bootstrap.STATE / JOURNAL
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        raw = json.dumps({"schema_version":1,"account":ACCOUNT,"label":label}, sort_keys=True).encode()
        require(os.write(fd, raw) == len(raw), "LEASE_JOURNAL_WRITE_REFUSED")
        os.fsync(fd)
    finally:
        os.close(fd)
    bootstrap.sync_state()


def cleanup(bootstrap):
    target = bootstrap.STATE / JOURNAL
    try:
        info = target.lstat()
    except FileNotFoundError:
        return False
    require(stat.S_ISREG(info.st_mode) and not target.is_symlink(), "LEASE_JOURNAL_REFUSED")
    value = bootstrap.parse(bootstrap.private_file(target, maximum=512))
    require(type(value) is dict and set(value) == {"schema_version","account","label"}
            and type(value["schema_version"]) is int and value["schema_version"] == 1
            and value["account"] == ACCOUNT and type(value["label"]) is str
            and LABEL.fullmatch(value["label"]), "LEASE_JOURNAL_REFUSED")
    sql(bootstrap, "revoke", value["label"])
    require(sql(bootstrap, "count", value["label"]) == 0, "LEASE_REVOCATION_REFUSED")
    target.unlink()
    bootstrap.sync_state()
    return True


@contextmanager
def repository_lease(bootstrap):
    with bootstrap.locked():
        bootstrap.validate_configuration()
        bootstrap.validate_running()
        bootstrap.cleanup()  # recover only the older helper's own stale lease
        cleanup(bootstrap)
        require(bootstrap.identity_attested() and bootstrap.sql("account")["eligible"], "TECHNICAL_ACCOUNT_REFUSED")
        label = "mrjam-rules-proposal-" + os.urandom(16).hex()
        require(sql(bootstrap, "count", label) == 0, "LEASE_COLLISION")
        publish(bootstrap, label)
        token = None
        try:
            raw = bootstrap.command([bootstrap.FORGEJO, "--config", str(bootstrap.INI),
                "admin", "user", "generate-access-token", "--username", ACCOUNT,
                "--token-name", label, "--scopes", SCOPES, "--raw"])
            require(re.fullmatch(rb"[0-9a-f]{40}\n", raw), "LEASE_TOKEN_REFUSED")
            token = raw[:-1].decode("ascii")
            # Native CLI creates an all-repository token. Narrow its resource
            # records transactionally BEFORE the first API or Git request.
            sql(bootstrap, "restrict", label)
            status, value = bootstrap.API(token).get("/api/v1/version")
            require(status == 200 and value == {"version":"17.0.1"}, "FORGEJO_VERSION_REFUSED")
            yield token
        finally:
            cleanup(bootstrap)
            if token is not None:
                require(bootstrap.API(token).get("/api/v1/user")[0] == 401, "LEASE_STILL_AUTHENTICATES")
