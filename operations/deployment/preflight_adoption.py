#!/usr/bin/env python3
"""Closed, read-only adoption metadata. No arguments; standalone over stdin.

Never execute discovered code, read secret/application contents, emit command
output, or accept SQL/paths/commands from the caller. Unknown is not absence.
ACME interpretation follows nixpkgs c5c4a43b0e80 security/acme/default.nix.
"""
import datetime
import grp
import ipaddress
import json
import os
import pwd
import re
import selectors
import shlex
import signal
import socket
import stat
import subprocess
import sys
import time

UNKNOWN = {"state": "unknown"}
ENVIRONMENT = {"PATH": "/run/current-system/sw/bin", "LANG": "C", "LC_ALL": "C"}
DEADLINE = None
STORE_OBJECT = r"/nix/store/[0-9a-df-np-sv-z]{32}-[A-Za-z0-9+._?=-]+"
STORE = re.compile(STORE_OBJECT + r"\Z")
STORE_PUBLIC = re.compile(STORE_OBJECT + r"(?:/[A-Za-z0-9._+@=-]+)*/?\Z")
HASH = re.compile(r"[0-9a-f]{20}\Z")
KNOWN_NAMES = ("postgres", "forgejo", "kanidm", "nextcloud", "nginx", "acme", "vision-auth",
               "vision", "vision-embeddings", "matheval", "audition")
ADOPTION_NAMES = ("mrjam-rust-blue", "mrjam-rust-green", "mrjam-vision-archive", "mrjam-vision-replay",
                  "mrjam-vision-cycle", "mrjam-vision-closure", "mrjam-vision-admission", "mrjam-metier", "mrj-auth")
NAMES = KNOWN_NAMES + ADOPTION_NAMES
UNITS = ("mrjam-metier", "vision", "vision-embeddings-backfill", "matheval", "vision-cycle",
         "vision-archive", "vision-replay", "vision-closure", "vision-admission", "forgejo-backup",
         "nextcloud-backup", "nextcloud-cron", "mrjam-sauvegarde", "mrjam-courriel",
         "vision-purge", "postgresqlBackup-matheval", "postgresqlBackup-nextcloud")
PATHS = {
    "identity_sessions": "/var/lib/mrjam-metier/log/sessions.sqlite",
    "kanidm_client_secret": "/var/lib/mrjam-identite/kanidm-vision.secret",
    "kanidm_admission_token": "/var/lib/mrjam-identite/kanidm-admission.token",
    "smtp_configuration": "/var/lib/mrjam-identite/proton-smtp.json",
    "matheval_setup_hash": "/var/lib/mrjam-metier/secrets/matheval-setup-hash",
    "archive_mail_state": "/var/lib/mrjam-vision-archive/courriels.sqlite",
    "cycle_mail_state": "/var/lib/mrjam-vision-cycle/courriels.sqlite",
    "admission_state": "/var/lib/mrjam-vision-admission/admissions.sqlite",
    "legacy_mail_state": "/var/lib/mrjam-metier/courriel/file.sqlite",
    "legacy_admission_requests": "/var/lib/mrjam-metier/admission/demandes.sqlite",
    "legacy_deletion_ledger": "/var/lib/mrjam-metier/effacements/demandes.jsonl",
    "legacy_cycle_configuration": "/var/lib/mrjam-identite/cycle.json",
    "closure_hook": "/var/lib/mrjam-identite/fermeture-hook.secret",
}
DATABASES = ("matheval", "vision", "vision_journal", "audition")
ROLES = ("matheval_app", "matheval_administration", "vision", "vision_administration", "vision_cycle",
         "vision_admission", "vision_fermeture", "vision_entretien", "vision_identite", "vision_journal_writer",
         "vision_journal_archiviste", "vision_journal_rejeu", "vision_journal_fermeture", "audition")
# Deliberately literal. No interpolation and no application-schema query.
CATALOG_SQL = """BEGIN READ ONLY;
SET LOCAL statement_timeout='3s';
SELECT
 EXISTS(SELECT 1 FROM pg_catalog.pg_database WHERE datname='matheval'),
 EXISTS(SELECT 1 FROM pg_catalog.pg_database WHERE datname='vision'),
 EXISTS(SELECT 1 FROM pg_catalog.pg_database WHERE datname='vision_journal'),
 EXISTS(SELECT 1 FROM pg_catalog.pg_database WHERE datname='audition'),
 EXISTS(SELECT 1 FROM pg_catalog.pg_roles WHERE rolname='matheval_app'),
 EXISTS(SELECT 1 FROM pg_catalog.pg_roles WHERE rolname='matheval_administration'),
 EXISTS(SELECT 1 FROM pg_catalog.pg_roles WHERE rolname='vision'),
 EXISTS(SELECT 1 FROM pg_catalog.pg_roles WHERE rolname='vision_administration'),
 EXISTS(SELECT 1 FROM pg_catalog.pg_roles WHERE rolname='vision_cycle'),
 EXISTS(SELECT 1 FROM pg_catalog.pg_roles WHERE rolname='vision_admission'),
 EXISTS(SELECT 1 FROM pg_catalog.pg_roles WHERE rolname='vision_fermeture'),
 EXISTS(SELECT 1 FROM pg_catalog.pg_roles WHERE rolname='vision_entretien'),
 EXISTS(SELECT 1 FROM pg_catalog.pg_roles WHERE rolname='vision_identite'),
 EXISTS(SELECT 1 FROM pg_catalog.pg_roles WHERE rolname='vision_journal_writer'),
 EXISTS(SELECT 1 FROM pg_catalog.pg_roles WHERE rolname='vision_journal_archiviste'),
 EXISTS(SELECT 1 FROM pg_catalog.pg_roles WHERE rolname='vision_journal_rejeu'),
 EXISTS(SELECT 1 FROM pg_catalog.pg_roles WHERE rolname='vision_journal_fermeture'),
 EXISTS(SELECT 1 FROM pg_catalog.pg_roles WHERE rolname='audition');
ROLLBACK;"""
LAYOUT_FIELDS = ("audition_app_role", "matheval_admin_role", "audition_schema", "audition_objects",
                 "audition_versions", "native_principal_function", "vision_gestion_schema", "vector_extension")
LAYOUT_SQL = """BEGIN READ ONLY;
SET LOCAL statement_timeout='3s';
SELECT
 EXISTS(SELECT 1 FROM pg_catalog.pg_roles WHERE rolname='audition_app'),
 EXISTS(SELECT 1 FROM pg_catalog.pg_roles WHERE rolname='matheval_admin'),
 pg_catalog.to_regnamespace('audition') IS NOT NULL,
 pg_catalog.to_regclass('audition.objets') IS NOT NULL,
 pg_catalog.to_regclass('audition.versions') IS NOT NULL,
 pg_catalog.to_regprocedure('vision_gestion.identifier(text,text)') IS NOT NULL,
 pg_catalog.to_regnamespace('vision_gestion') IS NOT NULL,
 EXISTS(SELECT 1 FROM pg_catalog.pg_extension WHERE extname='vector');
ROLLBACK;"""
# Constants transcribed from the received code declaration; comparisons only.
EXPECTED_HOSTNAME = "nixos"
EXPECTED_SYSTEM = "x86_64"
EXPECTED_ROOT_UUID = "f222513b-ded1-49fa-b591-20ce86a2fe7f"
EXPECTED_MAC = "d4:e8:d4:c3:50:d5"
EXPECTED_ADDRESSES = {"187.77.95.158/24", "2a02:4780:41:cf57::1/48"}
EXPECTED_GATEWAYS = {"187.77.95.254", "2a02:4780:41::1"}
EXPECTED_DNS = {"153.92.2.6", "1.1.1.1", "8.8.4.4"}


def run(arguments):
    """Bounded stdout, no stderr, fixed environment, no shell or input."""
    remaining = 5.0 if DEADLINE is None else min(5.0, DEADLINE - time.monotonic())
    if remaining <= 0:
        return None
    process = None
    try:
        process = subprocess.Popen(arguments, env=ENVIRONMENT, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                   start_new_session=True)
        end, data = time.monotonic() + remaining, bytearray()
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while True:
                left = end - time.monotonic()
                if left <= 0 or not selector.select(left):
                    return None
                chunk = os.read(process.stdout.fileno(), 8192)
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > 65536:
                    return None
        code = process.wait(timeout=max(0.01, end - time.monotonic()))
        return (code, data.decode("utf-8", "strict").strip())
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None
    finally:
        if process is not None:
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=1)
            process.stdout.close()


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("AMBIGUOUS_INPUT")
        result[key] = value
    return result


def command_json(arguments):
    result = run(arguments)
    if result is None or result[0] != 0:
        raise ValueError("UNKNOWN_COMMAND_RESULT")
    return json.loads(result[1], object_pairs_hook=unique_pairs)


def metadata(path):
    try:
        item = os.lstat(path)
        kind = ("file" if stat.S_ISREG(item.st_mode) else "directory" if stat.S_ISDIR(item.st_mode)
                else "symlink" if stat.S_ISLNK(item.st_mode) else "special")
        return {"state": "observed", "kind": kind, "uid": item.st_uid, "gid": item.st_gid,
                "mode": stat.S_IMODE(item.st_mode), "nonempty": item.st_size > 0}
    except FileNotFoundError:
        return {"state": "absent"}
    except OSError:
        return dict(UNKNOWN)


def read_regular(path, maximum, *, immutable=False):
    # /nix/store itself is trusted. No intermediate or final symlink is followed.
    if immutable and (not STORE_PUBLIC.fullmatch(path) or any(x in (".", "..") for x in path.split("/"))):
        raise ValueError("REFUSED_SOURCE_PATH")
    descriptor = open_components(path, directory=False)
    try:
        item = os.fstat(descriptor)
        if (not stat.S_ISREG(item.st_mode) or item.st_size > maximum
                or (immutable and (item.st_uid != 0 or stat.S_IMODE(item.st_mode) & 0o222))):
            raise ValueError("REFUSED_SOURCE")
        result = os.read(descriptor, maximum + 1)
        if len(result) > maximum:
            raise ValueError("REFUSED_SIZE")
        return result.decode("utf-8", "strict")
    finally:
        os.close(descriptor)


def open_components(path, *, directory):
    if not isinstance(path, str) or not path.startswith("/"):
        raise ValueError("ABSOLUTE_PATH_REQUIRED")
    parts = path.split("/")[1:]
    if not parts or any(part in ("", ".", "..") for part in parts):
        raise ValueError("REFUSED_PATH")
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for index, part in enumerate(parts):
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            if index < len(parts) - 1 or directory:
                flags |= os.O_DIRECTORY
            following = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = following
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def accounts():
    users, groups = {}, {}
    for name in NAMES:
        try:
            item = pwd.getpwnam(name)
            users[name] = {"state": "observed", "uid": item.pw_uid, "gid": item.pw_gid, "absent": False}
        except KeyError:
            users[name] = {"state": "absent", "absent": True}
        except OSError:
            users[name] = dict(UNKNOWN)
        try:
            item = grp.getgrnam(name)
            groups[name] = {"state": "observed", "gid": item.gr_gid, "absent": False}
        except KeyError:
            groups[name] = {"state": "absent", "absent": True}
        except OSError:
            groups[name] = dict(UNKNOWN)
    availability = {}
    for number in range(940, 971):
        result = {}
        for key, lookup in (("uid_available", pwd.getpwuid), ("gid_available", grp.getgrgid)):
            try:
                lookup(number)
                result[key] = False
            except KeyError:
                result[key] = True
            except OSError:
                result[key] = None
        availability[str(number)] = result
    return {"users": users, "groups": groups, "id_availability": availability}


def catalog():
    result = run(["runuser", "-u", "postgres", "--", "/run/current-system/sw/bin/psql",
                  "-X", "-w", "-q", "-A", "-t", "--set=ON_ERROR_STOP=1", "--host=/run/postgresql",
                  "--port=5432", "--dbname=postgres", "--command", CATALOG_SQL])
    if result is None or result[0] != 0:
        return dict(UNKNOWN)
    values = result[1].split("|")
    if len(values) != len(DATABASES) + len(ROLES) or any(value not in ("t", "f") for value in values):
        return dict(UNKNOWN)
    return {"state": "observed", "databases": dict(zip(DATABASES, (x == "t" for x in values[:4]))),
            "roles": dict(zip(ROLES, (x == "t" for x in values[4:])))}


def host_comparisons():
    result = {"hostname_matches": socket.gethostname() == EXPECTED_HOSTNAME,
              "system_matches": os.uname().machine == EXPECTED_SYSTEM,
              "grub_device_is_block": None, "root_uuid_matches": None, "root_fstype_matches": None,
              "interface_present": None, "mac_matches": None, "addresses_match": None,
              "gateways_match": None, "dns_matches": None}
    try:
        result["grub_device_is_block"] = stat.S_ISBLK(os.lstat("/dev/sda").st_mode)
    except FileNotFoundError:
        result["grub_device_is_block"] = False
    except OSError:
        pass
    try:
        document = command_json(["findmnt", "--json", "--mountpoint", "/", "--output", "UUID,FSTYPE"])
        records = document["filesystems"]
        if not isinstance(records, list) or len(records) != 1:
            raise ValueError("AMBIGUOUS_MOUNT")
        result["root_uuid_matches"] = records[0]["uuid"] == EXPECTED_ROOT_UUID
        result["root_fstype_matches"] = records[0]["fstype"] == "ext4"
    except (OSError, ValueError, KeyError, TypeError):
        pass
    try:
        links = command_json(["ip", "-json", "address", "show", "dev", "eth0"])
        if not isinstance(links, list) or len(links) != 1 or links[0]["ifname"] != "eth0":
            raise ValueError("AMBIGUOUS_INTERFACE")
        result["interface_present"] = True
        result["mac_matches"] = links[0]["address"].lower() == EXPECTED_MAC
        addresses = {str(ipaddress.ip_interface(entry["local"] + "/" + str(entry["prefixlen"])))
                     for entry in links[0]["addr_info"] if entry.get("scope") == "global"}
        result["addresses_match"] = addresses == EXPECTED_ADDRESSES
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        pass
    try:
        gateways = set()
        for family in ("-4", "-6"):
            routes = command_json(["ip", "-json", family, "route", "show", "default"])
            if not isinstance(routes, list) or len(routes) > 16:
                raise ValueError("AMBIGUOUS_ROUTES")
            for route in routes:
                if route.get("dev") == "eth0" and route.get("dst") == "default":
                    gateways.add(str(ipaddress.ip_address(route["gateway"])))
        result["gateways_match"] = gateways == EXPECTED_GATEWAYS
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        pass
    dns = run(["resolvectl", "dns", "eth0"])
    if dns is not None and dns[0] == 0:
        match = re.fullmatch(r"Link [0-9]+ \(eth0\): ([0-9A-Fa-f.: ]{1,256})", dns[1])
        if match:
            try:
                result["dns_matches"] = {str(ipaddress.ip_address(value)) for value in match[1].split()} == EXPECTED_DNS
            except ValueError:
                pass
    return result


def catalog_layout():
    result = run(["runuser", "-u", "postgres", "--", "/run/current-system/sw/bin/psql",
                  "-X", "-w", "-q", "-A", "-t", "--set=ON_ERROR_STOP=1", "--host=/run/postgresql",
                  "--port=5432", "--dbname=vision", "--command", LAYOUT_SQL])
    if result is None or result[0] != 0:
        return dict(UNKNOWN)
    values = result[1].split("|")
    if len(values) != len(LAYOUT_FIELDS) or any(value not in ("t", "f") for value in values):
        return dict(UNKNOWN)
    return {"state": "observed", "catalog_only": dict(zip(LAYOUT_FIELDS, (x == "t" for x in values)))}


def public_hostname():
    # Static machine metadata, never an account/person field.
    value = socket.gethostname()
    if re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", value):
        return {"state": "observed", "value": value}
    return dict(UNKNOWN)


def properties(unit, names):
    result = run(["systemctl", "show", unit] + ["--property=" + name for name in names])
    if result is None or result[0] != 0:
        raise ValueError("UNKNOWN_UNIT")
    pairs = []
    for line in result[1].splitlines():
        key, separator, value = line.partition("=")
        if not separator or key not in names:
            raise ValueError("AMBIGUOUS_UNIT")
        pairs.append((key, value))
    parsed = unique_pairs(pairs)
    if set(parsed) != set(names):
        raise ValueError("INCOMPLETE_UNIT")
    return parsed


def unit_states():
    result = {}
    for name in UNITS:
        try:
            values = properties(name + ".service", ("LoadState", "ActiveState"))
            if values["LoadState"] not in ("loaded", "not-found", "masked", "error", "bad-setting", "merged", "stub"):
                raise ValueError("UNKNOWN_LOAD_STATE")
            if values["ActiveState"] not in ("active", "reloading", "inactive", "failed", "activating", "deactivating", "maintenance", "refreshing"):
                raise ValueError("UNKNOWN_ACTIVE_STATE")
            result[name] = {"state": "observed", "loaded": values["LoadState"] == "loaded",
                            "active": values["ActiveState"] == "active"}
        except (OSError, ValueError, KeyError, TypeError):
            result[name] = dict(UNKNOWN)
    return result


def embeddings_metadata():
    try:
        values = properties("vision-embeddings.service", ("LoadState", "ActiveState", "ExecStart"))
        paths = re.findall(r"(?:^|[ {;])path=([^ ;}]+)", values["ExecStart"])
        arguments = re.findall(r"(?:^|[ ;])argv\[\]=([^;{}]+)", values["ExecStart"])
        if len(paths) != 1 or len(arguments) != 1:
            raise ValueError("AMBIGUOUS_EMBEDDINGS_COMMAND")
        tokens = shlex.split(arguments[0], posix=True)
        if len(tokens) != 4 or tokens[0] != paths[0] or tokens[2] != "--modele":
            raise ValueError("UNEXPECTED_EMBEDDINGS_ARGUMENTS")
        if not re.fullmatch(STORE_OBJECT + r"/bin/python(?:3(?:\.[0-9]{1,2})?)?", tokens[0]):
            raise ValueError("UNEXPECTED_PYTHON_PATH")
        if not STORE_PUBLIC.fullmatch(tokens[1]) or not tokens[1].endswith("/scripts/embeddings.py"):
            raise ValueError("UNEXPECTED_SCRIPT_PATH")
        if not STORE_PUBLIC.fullmatch(tokens[3]):
            raise ValueError("UNEXPECTED_MODEL_PATH")
        if any(any(part in (".", "..") for part in path.split("/")) for path in (tokens[0], tokens[1], tokens[3])):
            raise ValueError("REFUSED_REFERENCE_TRAVERSAL")
        if values["LoadState"] not in ("loaded", "not-found") or values["ActiveState"] not in ("active", "inactive", "failed"):
            raise ValueError("UNKNOWN_PROVIDER_STATE")
        return {"state": "observed", "loaded": values["LoadState"] == "loaded", "active": values["ActiveState"] == "active",
                "python": tokens[0], "script": tokens[1], "model": tokens[3]}
    except (OSError, ValueError, KeyError, TypeError):
        return dict(UNKNOWN)


def nginx_tokens(text):
    tokens, current, quote, index = [], [], None, 0
    while index < len(text):
        char = text[index]
        if char == "\\":
            index += 1
            if index >= len(text):
                raise ValueError("TRUNCATED_CONFIG")
            current.append(text[index])
        elif quote:
            if char == quote:
                quote = None
            else:
                current.append(char)
        elif char in "\"'":
            quote = char
        elif char == "#":
            end = text.find("\n", index)
            index = len(text) if end < 0 else end
            continue
        elif char.isspace() or char in "{};":
            if current:
                tokens.append("".join(current))
                current = []
            if char in "{};":
                tokens.append(char)
        else:
            current.append(char)
        if len(current) > 16384 or len(tokens) > 100000:
            raise ValueError("CONFIG_LIMIT")
        index += 1
    if quote or current:
        raise ValueError("TRUNCATED_CONFIG")
    return tokens


def nginx_tree(text):
    tokens = nginx_tokens(text)
    index = 0
    def block(depth, nested):
        nonlocal index
        if depth > 20:
            raise ValueError("CONFIG_DEPTH")
        nodes, directive = [], []
        while index < len(tokens):
            value = tokens[index]
            index += 1
            if value == "}":
                if directive or not nested:
                    raise ValueError("AMBIGUOUS_CONFIG")
                return nodes
            if value in ("{", ";"):
                if not directive:
                    raise ValueError("EMPTY_DIRECTIVE")
                nodes.append((directive, block(depth + 1, True) if value == "{" else None))
                directive = []
            else:
                directive.append(value)
        if nested or directive:
            raise ValueError("TRUNCATED_CONFIG")
        return nodes
    return block(0, False)


def public_path(value):
    if len(value) > 512 or any(part in (".", "..") for part in value.split("/")):
        return None
    if STORE_PUBLIC.fullmatch(value):
        return value
    if re.fullmatch(r"/srv/[A-Za-z0-9._/-]{1,160}", value) and "//" not in value:
        return value
    if value.rstrip("/") in ("/var/lib/acme/acme-challenge", "/var/www", "/usr/share/nginx/html"):
        return value
    return None


def public_domain(value):
    if not isinstance(value, str) or not 4 <= len(value) <= 253:
        return False
    labels = value.split(".")
    return (2 <= len(labels) <= 16 and labels[-1] not in ("invalid", "test", "localhost", "local", "internal", "example", "onion")
            and re.fullmatch(r"[a-z]{2,63}", labels[-1]) is not None
            and all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in labels))


def public_selector(tokens):
    if len(tokens) == 1:
        modifier, path = "", tokens[0]
    elif len(tokens) == 2 and tokens[0] in ("=", "^~"):
        modifier, path = tokens
    else:
        return None
    if not re.fullmatch(r"/[A-Za-z0-9_./=-]{0,160}", path) or any(p in (".", "..") for p in path.split("/")):
        return None
    return (modifier + " " + path).strip()


def nginx_metadata():
    try:
        raw = properties("nginx.service", ("ExecStart",))["ExecStart"]
        candidates = re.findall(r"(?:^|\s)-c\s+(\S+)", raw)
        if len(candidates) != 1 or not STORE.fullmatch(candidates[0]) or not candidates[0].endswith("-nginx.conf"):
            raise ValueError("AMBIGUOUS_NGINX_SOURCE")
        contents = read_regular(candidates[0], 1024 * 1024, immutable=True)
        tree = nginx_tree(contents)
        output = {}
        def servers(nodes):
            for words, children in nodes:
                if words == ["server"] and children is not None:
                    yield children
                elif children is not None:
                    yield from servers(children)
        for server in servers(tree):
            names = [words[1:] for words, children in server if children is None and words[0] == "server_name"]
            if len(names) != 1:
                if names:
                    raise ValueError("AMBIGUOUS_SERVER_NAME")
                continue
            known = sorted({name for name in names[0] if public_domain(name)})
            if not known:
                continue
            entry = {"root": None, "locations": [], "unreported_mapping_present": False,
                     "includes_present": any(words[0] == "include" for words, _ in server)}
            roots = [words for words, child in server if words[0] == "root" and child is None]
            if len(roots) > 1 or any(len(words) != 2 for words in roots):
                raise ValueError("AMBIGUOUS_ROOT")
            if roots:
                entry["root"] = public_path(roots[0][1])
                entry["unreported_mapping_present"] = entry["root"] is None
            selectors_seen = set()
            for words, children in server:
                if words[0] != "location" or children is None:
                    continue
                selector = public_selector(words[1:])
                mappings = [(statement, nested) for statement, nested in children if statement[0] in ("root", "alias")]
                if not mappings:
                    continue
                if len(mappings) != 1 or len(mappings[0][0]) != 2 or mappings[0][1] is not None:
                    raise ValueError("AMBIGUOUS_LOCATION_MAPPING")
                field, value = mappings[0][0]
                value = public_path(value)
                if selector is None or value is None:
                    entry["unreported_mapping_present"] = True
                    continue
                if selector in selectors_seen:
                    raise ValueError("DUPLICATE_LOCATION")
                selectors_seen.add(selector)
                entry["locations"].append({"selector": selector, field: value})
            if len(entry["locations"]) > 64:
                raise ValueError("MAPPING_LIMIT")
            for name in known:
                output.setdefault(name, []).append(entry)
                if len(output[name]) > 4 or len(output) > 32:
                    raise ValueError("SERVER_LIMIT")
        return {"state": "observed", "selected_configuration": candidates[0], "public_hosts": output,
                "includes_followed": False}
    except (OSError, ValueError, KeyError, TypeError):
        return dict(UNKNOWN)


def acme_script_path(value, domain):
    if not public_domain(domain):
        raise ValueError("UNKNOWN_DOMAIN")
    paths = re.findall(r"(?:^|[ {;])path=([^ ;}]+)", value)
    arguments = re.findall(r"(?:^|[ ;])argv\[\]=([^;{}]+)", value)
    if len(paths) != 1 or len(arguments) != 1 or arguments[0].strip() != paths[0]:
        raise ValueError("AMBIGUOUS_EXEC_START")
    suffix = "acme-order-renew-" + domain + "-start"
    expected = STORE_OBJECT + r"/bin/" + re.escape(suffix)
    if not re.fullmatch(expected, paths[0]) or not paths[0].split("/")[3].endswith("-unit-script-" + suffix):
        raise ValueError("REFUSED_ACME_SCRIPT")
    return paths[0]


def acme_layout(properties_value, domain):
    states = properties_value["StateDirectory"].split()
    binds = properties_value["BindPaths"].split()
    base = "acme/.lego/" + domain + "/"
    certificates = [item[len(base):] for item in states if item.startswith(base)]
    accounts_found = [item[len("acme/.lego/accounts/"):] for item in states if item.startswith("acme/.lego/accounts/")]
    if (len(certificates) != 1 or len(accounts_found) != 1 or not HASH.fullmatch(certificates[0])
            or not HASH.fullmatch(accounts_found[0]) or len(states) != 4 or len(set(states)) != 4
            or "acme/" + domain not in states or "acme/.lego/" + domain not in states):
        raise ValueError("AMBIGUOUS_ACME_STATE")
    account, certificate = accounts_found[0], certificates[0]
    wanted = {"/var/lib/acme/.lego/accounts/" + account + ":/tmp/accounts",
              "/var/lib/acme/" + domain + ":/tmp/out",
              "/var/lib/acme/.lego/" + domain + "/" + certificate + ":/tmp/certificates"}
    # systemd normalizes the optional recursive-bind suffix on some releases.
    normalized = [item[:-6] if item.endswith(":rbind") else item for item in binds]
    if len(normalized) != 3 or set(normalized) != wanted:
        raise ValueError("INCONSISTENT_ACME_BINDS")
    return account, certificate


def lego_options(arguments, expected_mode):
    tokens = shlex.split(arguments, posix=True)
    if len(tokens) > 128 or any(len(value) > 1024 for value in tokens):
        raise ValueError("LEGO_OPTIONS_LIMIT")
    values, domains, extra, mode, index = {}, [], False, None, 0
    valued = {"--path", "--email", "--http.webroot", "--server", "--key-type", "--days"}
    switches = {"--accept-tos", "--http", "--no-random-sleep", "--dynamic"}
    seen_switches = set()
    while index < len(tokens):
        item = tokens[index]
        index += 1
        if item in ("run", "renew"):
            if mode is not None:
                raise ValueError("AMBIGUOUS_LEGO_MODE")
            mode = item
        elif item in switches:
            if item in seen_switches:
                raise ValueError("DUPLICATE_LEGO_OPTION")
            seen_switches.add(item)
        elif item in valued or item == "-d":
            if index >= len(tokens):
                raise ValueError("MISSING_LEGO_VALUE")
            value = tokens[index]
            index += 1
            if item == "-d":
                if not public_domain(value) or value in domains:
                    raise ValueError("UNKNOWN_OR_DUPLICATE_DOMAIN")
                domains.append(value)
            else:
                if item in values:
                    raise ValueError("DUPLICATE_LEGO_OPTION")
                values[item] = value
        else:
            # Never export unknown flag names/values, which may be credentials.
            extra = True
    if (mode != expected_mode or values.get("--path") != "." or not domains
            or "--accept-tos" not in seen_switches or "--http" not in seen_switches):
        raise ValueError("UNSUPPORTED_LEGO_PROFILE")
    keytype = values.get("--key-type")
    if keytype not in ("ec256", "ec384", "rsa2048", "rsa3072", "rsa4096", "rsa8192"):
        raise ValueError("UNSUPPORTED_KEYTYPE")
    server = values.get("--server", "https://acme-v02.api.letsencrypt.org/directory")
    if server not in ("https://acme-v02.api.letsencrypt.org/directory", "https://acme-staging-v02.api.letsencrypt.org/directory"):
        raise ValueError("UNSUPPORTED_ACME_SERVER")
    webroot = values.get("--http.webroot", "")
    if webroot.rstrip("/") != "/var/lib/acme/acme-challenge":
        raise ValueError("UNSUPPORTED_HTTP_WEBROOT")
    if "--days" in values and not re.fullmatch(r"[0-9]{1,4}", values["--days"]):
        raise ValueError("AMBIGUOUS_RENEWAL_DAYS")
    return {"domain": domains[0], "sans": domains[1:], "server_url": server,
            "server_explicit": "--server" in values, "key_type": keytype, "http_webroot": webroot,
            "extra_flags_present": extra}


def acme_options(script, domain):
    lines = script.replace("\\\n", " ").splitlines()
    commands = []
    for line in lines:
        match = re.fullmatch(r"\s*(?:if|elif)\s+!\s+lego\s+(.+);\s*then\s*", line)
        if match:
            commands.append(match[1])
    if len(commands) != 2:
        raise ValueError("AMBIGUOUS_LEGO_COMMANDS")
    renew, run_options = lego_options(commands[0], "renew"), lego_options(commands[1], "run")
    renew_extra, run_extra = renew.pop("extra_flags_present"), run_options.pop("extra_flags_present")
    extra = renew_extra or run_extra
    if renew != run_options or run_options["domain"] != domain:
        raise ValueError("INCONSISTENT_LEGO_COMMANDS")
    return dict(run_options, extra_flags_present=extra)


def account_material(account_hash):
    if not HASH.fullmatch(account_hash):
        return dict(UNKNOWN)
    try:
        descriptor = open_components("/var/lib/acme/.lego/accounts/" + account_hash, directory=True)
    except FileNotFoundError:
        return {"state": "absent", "unique_key_present": False, "unique_registration_present": False,
                "matching_unique_pair": False}
    except (OSError, ValueError):
        return dict(UNKNOWN)
    keys, registrations, count = [], [], [0]
    def visit(directory, depth, relative=()):
        if depth > 6:
            raise ValueError("ACCOUNT_METADATA_DEPTH")
        with os.scandir(directory) as entries:
            for entry in entries:
                count[0] += 1
                if count[0] > 128:
                    raise ValueError("ACCOUNT_METADATA_LIMIT")
                item = entry.stat(follow_symlinks=False)
                if stat.S_ISDIR(item.st_mode):
                    child = os.open(entry.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
                    try:
                        visit(child, depth + 1, relative + (entry.name,))
                    finally:
                        os.close(child)
                elif stat.S_ISREG(item.st_mode) and item.st_size > 0:
                    if entry.name.endswith(".key"):
                        keys.append(relative + (entry.name,))
                    elif entry.name == "account.json":
                        registrations.append(relative + (entry.name,))
                else:
                    raise ValueError("UNEXPECTED_ACCOUNT_ENTRY")
    try:
        visit(descriptor, 0)
        return {"state": "observed", "unique_key_present": len(keys) == 1,
                "unique_registration_present": len(registrations) == 1,
                "matching_unique_pair": len(keys) == len(registrations) == 1 and len(keys[0]) >= 2
                and keys[0][-2] == "keys" and keys[0][:-2] + ("account.json",) == registrations[0]}
    except (OSError, ValueError):
        return dict(UNKNOWN)
    finally:
        os.close(descriptor)


def acme_timer(domain):
    try:
        values = properties("acme-renew-" + domain + ".timer", ("TimersCalendar", "RandomizedDelayUSec"))
        calendars = re.findall(r"OnCalendar=([^;{}]+)", values["TimersCalendar"])
        if len(calendars) != 1:
            raise ValueError("AMBIGUOUS_CALENDAR")
        calendar = calendars[0].strip()
        if not (calendar in ("daily", "weekly", "monthly", "yearly", "hourly")
                or re.fullmatch(r"[0-9*,:./~+ -]{1,100}(?: UTC)?", calendar)):
            raise ValueError("UNSUPPORTED_CALENDAR")
        jitter = values["RandomizedDelayUSec"]
        if not re.fullmatch(r"[0-9]+(?:us|ms|s|min|h|d|w|y)(?: [0-9]+(?:us|ms|s|min|h|d|w|y))*", jitter) or len(jitter) > 64:
            raise ValueError("UNSUPPORTED_JITTER")
        return {"state": "observed", "calendar": calendar, "randomized_delay": jitter}
    except (OSError, ValueError, KeyError, TypeError):
        return dict(UNKNOWN)


def acme_metadata(domain):
    try:
        if not public_domain(domain):
            raise ValueError("UNKNOWN_DOMAIN")
        values = properties("acme-order-renew-" + domain + ".service", ("StateDirectory", "BindPaths", "ExecStart"))
        account, certificate = acme_layout(values, domain)
        source = acme_script_path(values["ExecStart"], domain)
        options = acme_options(read_regular(source, 131072, immutable=True), domain)
        return dict(options, state="observed", account_hash=account, certificate_directory_hash=certificate,
                    account_material=account_material(account), timer=acme_timer(domain))
    except (OSError, ValueError, KeyError, TypeError):
        return dict(UNKNOWN)


def collect():
    global DEADLINE
    DEADLINE = time.monotonic() + 110
    nginx = nginx_metadata()
    domains = sorted(nginx.get("public_hosts", {}))
    return {"schema_version": 1, "authority": "bounded-read-only-adoption-observation",
            "recorded_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "accounts": accounts(), "paths": {name: metadata(path) for name, path in PATHS.items()},
            "postgres_catalog": catalog(), "postgres_layout": catalog_layout(),
            "received_profile_comparisons": host_comparisons(), "hostname": public_hostname(),
            "units": unit_states(), "embeddings": embeddings_metadata(), "nginx": nginx,
            "acme_domain_selection_state": nginx["state"], "acme": {domain: acme_metadata(domain) for domain in domains},
            "application_data_read": False, "secret_contents_read": False, "logs_read": False,
            "production_mutation": False, "discovered_scripts_executed": False}


def deadline_expired(_signal, _frame):
    raise RuntimeError("PREFLIGHT_DEADLINE")


if __name__ == "__main__":
    if len(sys.argv) != 1 or os.geteuid() != 0:
        raise SystemExit(64)
    try:
        signal.signal(signal.SIGALRM, deadline_expired)
        signal.alarm(120)
        output = json.dumps(collect(), sort_keys=True, separators=(",", ":"))
        if len(output.encode()) > 65536:
            raise ValueError("OUTPUT_LIMIT")
        print(output)
    except Exception:
        print('{"schema_version":1,"state":"unknown","code":"ADOPTION_PREFLIGHT_REFUSED"}')
        raise SystemExit(65)
