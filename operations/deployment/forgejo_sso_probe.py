#!/usr/bin/env python3
"""Closed, read-only verification of the retained Forgejo native SSO binding.

No CLI arguments or environment-selected paths. The private binding stays on
the host; only a fixed object of booleans can be returned. No provider request,
account change, credential creation or legacy helper is used.
"""
import json
import os
from pathlib import Path
import re
import resource
import signal
import stat
import subprocess
import sys

BINDING = Path("/var/lib/forgejo-identity/client.json")
PSQL = "/run/current-system/sw/bin/psql"
DISCOVERY = "https://log.mrj.am/oauth2/openid/mrjam-forgejo/.well-known/openid-configuration"
CHECKS = ("binding_file_valid", "one_active_native_provider", "client_id_preserved",
          "discovery_preserved", "provider_secret_present", "owner_binding_preserved",
          "owner_login_enabled", "owner_local_login_disabled")
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z")


class Refused(Exception):
    pass


def strict(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise Refused()
        value[key] = item
    return value


def subject_from_binding(path=BINDING, uid=0, gid=0):
    """Read through protected directory descriptors, returning only the UUID."""
    path = Path(path)
    if not path.is_absolute() or any(part in (".", "..") for part in path.parts):
        raise Refused()
    directory = os.open("/", os.O_DIRECTORY | os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        for part in path.parts[1:-1]:
            next_directory = os.open(part, os.O_DIRECTORY | os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                     dir_fd=directory)
            os.close(directory)
            directory = next_directory
            metadata = os.fstat(directory)
            if metadata.st_uid not in (0, uid) or metadata.st_mode & 0o022:
                raise Refused()
        parent = os.fstat(directory)
        if parent.st_uid != uid or parent.st_gid != gid or stat.S_IMODE(parent.st_mode) != 0o700:
            raise Refused()
        descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
                             dir_fd=directory)
        with os.fdopen(descriptor, "rb") as stream:
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != uid or metadata.st_gid != gid \
                    or metadata.st_nlink != 1 or stat.S_IMODE(metadata.st_mode) != 0o600:
                raise Refused()
            data = stream.read(16385)
            if len(data) > 16384:
                raise Refused()
    finally:
        os.close(directory)
    binding = json.loads(data, object_pairs_hook=strict)
    if not isinstance(binding, dict) or set(binding) != {"clientId", "clientSecret", "ownerSubject"} \
            or binding["clientId"] != "mrjam-forgejo" \
            or not isinstance(binding["clientSecret"], str) or not 20 <= len(binding["clientSecret"]) <= 4096 \
            or not isinstance(binding["ownerSubject"], str) or not UUID.fullmatch(binding["ownerSubject"]):
        raise Refused()
    return binding["ownerSubject"]


def query(subject):
    if not isinstance(subject, str) or not UUID.fullmatch(subject):
        raise Refused()
    # Only the validated UUID is inserted, through stdin, never argv. Values
    # selected from private rows never leave PostgreSQL: every output is boolean.
    return ("""BEGIN READ ONLY;
SET LOCAL statement_timeout='5s';
SET LOCAL lock_timeout='2s';
SET LOCAL search_path=pg_catalog;
WITH native AS (
 SELECT id,type,is_active,CASE WHEN cfg IS JSON OBJECT WITH UNIQUE KEYS
   THEN cfg::jsonb ELSE '{}'::jsonb END AS parameters
 FROM public.login_source WHERE name='Kanidm'
), owner_account AS (
 SELECT login_type,login_source,login_name,is_admin,is_active,prohibit_login,must_change_password,type
 FROM public."user" WHERE lower_name IN ('mrjam','mrjam-admin')
)
SELECT json_build_object(
 'binding_file_valid',true,
 'one_active_native_provider',(SELECT count(*)=1 AND coalesce(bool_and(type=6 AND is_active),false) FROM native)
   AND (SELECT count(*)=1 FROM public.login_source WHERE is_active),
 'client_id_preserved',(SELECT count(*)=1 AND coalesce(bool_and(parameters->>'Provider'='openidConnect'
   AND parameters->>'ClientID'='mrjam-forgejo'),false) FROM native),
 'discovery_preserved',(SELECT count(*)=1 AND coalesce(bool_and(parameters->>'OpenIDConnectAutoDiscoveryURL'=
   'https://log.mrj.am/oauth2/openid/mrjam-forgejo/.well-known/openid-configuration'),false) FROM native),
 'provider_secret_present',(SELECT count(*)=1 AND coalesce(bool_and(jsonb_typeof(parameters->'ClientSecret')='string'
   AND length(parameters->>'ClientSecret') BETWEEN 20 AND 4096),false) FROM native),
 'owner_binding_preserved',(SELECT count(*)=1 AND coalesce(bool_and(type=0 AND is_admin AND login_type=6
   AND login_name='%s' AND login_source IN (SELECT id FROM native)),false) FROM owner_account),
 'owner_login_enabled',(SELECT count(*)=1 AND coalesce(bool_and(is_active AND NOT prohibit_login
   AND NOT must_change_password),false) FROM owner_account),
 'owner_local_login_disabled',(SELECT count(*)=1 AND coalesce(bool_and(login_type=6
   AND login_source IN (SELECT id FROM native)),false) FROM owner_account)
);
ROLLBACK;
""" % subject).encode("ascii")


def parse_result(data):
    if not isinstance(data, bytes) or len(data) > 2048:
        raise Refused()
    value = json.loads(data, object_pairs_hook=strict)
    if not isinstance(value, dict) or set(value) != set(CHECKS) \
            or any(type(item) is not bool for item in value.values()):
        raise Refused()
    return value


def inspect():
    subject = subject_from_binding()
    process = subprocess.run([PSQL, "-X", "-w", "-qAt", "--set=ON_ERROR_STOP=1",
                              "--host=/run/postgresql", "--port=5432", "--dbname=forgejo"],
                             input=query(subject), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             timeout=15, check=False, user=71, group=71, extra_groups=[],
                             env={"HOME":"/var/empty", "USER":"postgres", "LOGNAME":"postgres",
                                  "LANG":"C", "LC_ALL":"C", "TZ":"UTC"})
    if process.returncode != 0:
        raise Refused()
    return parse_result(process.stdout)


def main():
    if len(sys.argv) != 1 or os.geteuid() != 0:
        return 64
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(Refused()))
    signal.alarm(20)
    try:
        checks = inspect()
        result = {"schema_version":1,"code":"SSO_CHECKED", "checks":checks,
                  "passed":all(checks.values()),"private_values_exported":False,"mutation_performed":False}
    except Exception:
        result = {"schema_version":1,"code":"SSO_CHECK_UNAVAILABLE", "checks":{},
                  "passed":False,"private_values_exported":False,"mutation_performed":False}
    finally:
        signal.alarm(0)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
