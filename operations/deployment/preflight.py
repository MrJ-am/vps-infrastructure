#!/usr/bin/env python3
"""Fixed read-only installation metadata for the first MRJ.am deployment.

No arguments, SQL, secrets, application records, logs, write or service action.
Only closed field names, numeric metadata and validated public store paths leave
the host. Run using the already delivered pinned Python, over verified SSH.
"""
import datetime
import json
import os
import pwd
import re
import shutil
import stat
import subprocess
import sys

STORE = re.compile(r"/nix/store/[0-9a-df-np-sv-z]{32}-[A-Za-z0-9+._?=-]+\Z")
DOMAIN = re.compile(r"(?:[a-z0-9-]+\.)*mrj\.am\Z")
PREVIOUS = "/nix/store/jn9rf2fgk2y6dbhdnjwkmfww3pchkyb9-nixos-system-nixos-26.05.8639.c5c4a43b0e80"
ACCOUNTS = ("postgres", "forgejo", "kanidm", "nextcloud", "nginx", "acme",
            "mrj-auth", "vision-auth", "vision", "vision-embeddings", "matheval", "audition")
UNITS = ("mrj-auth", "vision-embeddings", "vision-archive", "vision-replay", "vision-cycle",
         "vision-closure", "vision-admission", "forgejo-backup", "nextcloud-backup")
PATHS = {
    "postgres_cluster": "/var/lib/postgresql/17",
    "forgejo_state": "/var/lib/forgejo",
    "forgejo_repositories": "/var/lib/forgejo/repositories",
    "forgejo_secret_key": "/var/lib/forgejo/custom/conf/secret_key",
    "forgejo_internal_token": "/var/lib/forgejo/custom/conf/internal_token",
    "forgejo_oauth2_jwt_secret": "/var/lib/forgejo/custom/conf/oauth2_jwt_secret",
    "kanidm_database": "/var/lib/kanidm/kanidm.db",
    "nextcloud_state": "/var/lib/nextcloud",
    "nextcloud_config": "/var/lib/nextcloud/config/config.php",
    "nextcloud_data": "/var/lib/nextcloud/data",
    "nextcloud_containment_marker": "/var/lib/nextcloud-php-security/blocked",
    "authentication_state": "/var/lib/mrj-auth",
    "authentication_sessions": "/var/lib/mrj-auth/sessions.sqlite",
    "vision_state": "/var/lib/vision",
    "backup_directory": "/var/backup",
}
ENVIRONMENT = {"PATH": "/run/current-system/sw/bin", "LANG": "C", "LC_ALL": "C"}


def run(arguments):
    try:
        result = subprocess.run(arguments, env=ENVIRONMENT, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                timeout=15, check=False)
        if len(result.stdout) > 65536:
            return None
        return result.returncode, result.stdout.decode("utf-8", "strict").strip()
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def metadata(path):
    try:
        item = os.stat(path, follow_symlinks=False)
        kind = ("file" if stat.S_ISREG(item.st_mode) else "directory" if stat.S_ISDIR(item.st_mode)
                else "symlink" if stat.S_ISLNK(item.st_mode) else "special")
        return {"state": "observed", "kind": kind, "uid": item.st_uid, "gid": item.st_gid,
                "mode": stat.S_IMODE(item.st_mode), "nonempty": item.st_size > 0}
    except FileNotFoundError:
        return {"state": "absent"}
    except OSError:
        return {"state": "unknown"}


def read_small_regular(path, maximum):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
            raise ValueError("REFUSED_INPUT")
        data = os.read(descriptor, maximum + 1)
        if len(data) > maximum:
            raise ValueError("REFUSED_INPUT")
        return data.decode("utf-8", "strict")
    finally:
        os.close(descriptor)


def nginx_public_metadata():
    # Read only the immutable public Nginx configuration selected by its unit.
    # Never export the command line or arbitrary configuration text.
    result = run(["systemctl", "show", "nginx.service", "--property=ExecStart", "--value"])
    if result is None or result[0] != 0:
        return {"state": "unknown"}
    matches = re.findall(r"(?:-c\s+)(/nix/store/[0-9a-df-np-sv-z]{32}-[A-Za-z0-9+._?=-]+)", result[1])
    if len(matches) != 1 or not STORE.fullmatch(matches[0]) or not matches[0].endswith("nginx.conf"):
        return {"state": "unknown"}
    try:
        contents = read_small_regular(matches[0], 1024 * 1024)
        domains = sorted({value for declaration in re.findall(r"\bserver_name\s+([^;]+);", contents)
                          for value in declaration.split() if DOMAIN.fullmatch(value)})
        roots = sorted({value for value in re.findall(r"\broot\s+(/nix/store/[^\s;]+)\s*;", contents)
                        if STORE.fullmatch(value) and "nextcloud" in value})
        if len(domains) > 32 or len(roots) > 8:
            raise ValueError("REFUSED_OUTPUT")
        return {"state": "observed", "public_domains": domains, "nextcloud_webroots": roots,
                "identity_port_3002_declared": bool(re.search(r"\blisten\s+127\.0\.0\.1:3002\b", contents))}
    except (OSError, ValueError):
        return {"state": "unknown"}


def collect():
    generation = os.path.realpath("/run/current-system")
    if not STORE.fullmatch(generation):
        raise ValueError("GENERATION_REFUSED")
    accounts = {}
    for name in ACCOUNTS:
        try:
            entry = pwd.getpwnam(name)
            accounts[name] = {"state": "observed", "uid": entry.pw_uid, "gid": entry.pw_gid}
        except KeyError:
            accounts[name] = {"state": "absent"}
    units = {}
    for name in UNITS:
        result = run(["systemctl", "show", name + ".service", "--property=LoadState", "--property=ActiveState"])
        fields = dict(line.split("=", 1) for line in result[1].splitlines() if "=" in line) if result and result[0] == 0 else {}
        load = fields.get("LoadState")
        active = fields.get("ActiveState")
        units[name] = ({"state": "observed", "loaded": load == "loaded", "active": active == "active"}
                       if load in ("loaded", "not-found", "masked", "error", "bad-setting", "merged", "stub")
                       and active in ("active", "reloading", "inactive", "failed", "activating", "deactivating", "maintenance", "refreshing")
                       else {"state": "unknown"})
    try:
        pg17 = read_small_regular("/var/lib/postgresql/17/PG_VERSION", 16).strip() == "17"
    except (OSError, ValueError):
        pg17 = False
    paths = {name: metadata(path) for name, path in PATHS.items()}
    for domain in ("forge.mrj.am", "log.mrj.am", "cloud.mrj.am"):
        paths["certificate_" + domain] = metadata("/var/lib/acme/" + domain + "/fullchain.pem")
        paths["certificate_key_" + domain] = metadata("/var/lib/acme/" + domain + "/key.pem")
    identity_probes = {}
    for endpoint in ("verify", "verify-mcp", "verify-gestion"):
        probe = run(["curl", "--silent", "--noproxy", "*", "--max-time", "3", "--output", "/dev/null",
                     "--write-out", "%{http_code}", "--header", "Host: mrj-auth.internal",
                     "--header", "X-Forwarded-Host: vision.mrj.am", "--header", "X-Forwarded-Proto: https",
                     "--header", "X-Original-Method: GET", "http://127.0.0.1:3002/" + endpoint])
        identity_probes[endpoint] = (int(probe[1]) if probe and probe[0] == 0
                                    and re.fullmatch(r"[1-5][0-9]{2}", probe[1]) else None)
    return {"schema_version": 1, "authority": "bounded-read-only-ssh-observation",
            "recorded_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "generation": generation, "generation_matches_previous": generation == PREVIOUS,
            "postgres_major_17": pg17, "accounts": accounts, "units": units, "paths": paths,
            "nginx": nginx_public_metadata(), "identity_unauthenticated_http_status": identity_probes,
            "root_free_bytes": shutil.disk_usage("/").free,
            "production_data_read": False, "secrets_read": False, "production_mutation": False}


if __name__ == "__main__":
    if len(sys.argv) != 1 or os.geteuid() != 0:
        raise SystemExit(64)
    try:
        print(json.dumps(collect(), sort_keys=True, separators=(",", ":")))
    except Exception:
        print('{"schema_version":1,"code":"PREFLIGHT_REFUSED"}')
        raise SystemExit(65)
