"""Closed, code-only service observation contract. No application records."""
import json
import re

ACCOUNTS = ("forgejo", "kanidm", "nextcloud", "postgres", "etp_carnet", "mrjam-metier")
UNITS = ("forgejo", "kanidm", "phpfpm-nextcloud", "postgresql", "vise", "mrjam-metier", "nginx")
STORE = re.compile(r"/nix/store/[0-9abcdfghijklmnpqrsvwxyz]{32}-[A-Za-z0-9+._?=\-]{1,211}")
EXECUTABLE = re.compile(STORE.pattern + r"(?:/[A-Za-z0-9+._=\-]{1,100}){1,5}")
MAX_BYTES = 16384


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def validate(value):
    if type(value) is not dict or set(value) != {"schema_version", "authority", "accounts", "services", "generation"}:
        raise ValueError("shape")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1 or value["authority"] != "unverified_observation":
        raise ValueError("authority")
    if type(value["accounts"]) is not dict or set(value["accounts"]) != set(ACCOUNTS):
        raise ValueError("accounts")
    for account in value["accounts"].values():
        if type(account) is not dict or set(account) != {"state", "uid", "gid"}:
            raise ValueError("account")
        if account["state"] == "observed":
            if not all(type(account[x]) is int and 1 <= account[x] < 2**31 for x in ("uid", "gid")):
                raise ValueError("identity")
        elif account["state"] not in ("unknown", "absent") or account["uid"] is not None or account["gid"] is not None:
            raise ValueError("unknown identity")
    if type(value["services"]) is not dict or set(value["services"]) != set(UNITS):
        raise ValueError("services")
    for service in value["services"].values():
        if type(service) is not dict or set(service) != {"state", "executable", "store_path", "nar_hash", "nar_size"}:
            raise ValueError("service")
        if service["state"] not in ("active", "inactive", "failed", "unknown", "absent"):
            raise ValueError("state")
        metadata(service)
        exe = service["executable"]
        if exe is not None and (type(exe) is not str or EXECUTABLE.fullmatch(exe) is None
            or service["store_path"] is None or "/../" in exe or "/./" in exe or exe.split("/")[3] != service["store_path"].split("/")[3]):
            raise ValueError("executable")
        if service["state"] != "active" and exe is not None:
            raise ValueError("inactive executable")
    metadata(value["generation"], exact=True)
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    if len(encoded) > MAX_BYTES:
        raise ValueError("size")
    return encoded


def metadata(record, exact=False):
    if type(record) is not dict or (exact and set(record) != {"store_path", "nar_hash", "nar_size"}):
        raise ValueError("metadata")
    path = record["store_path"]
    if path is not None and (type(path) is not str or STORE.fullmatch(path) is None):
        raise ValueError("store")
    nar_hash, nar_size = record["nar_hash"], record["nar_size"]
    if nar_hash is None and nar_size is None:
        return
    if path is None or type(nar_hash) is not str or re.fullmatch(r"sha256-[A-Za-z0-9+/]{43}=", nar_hash) is None:
        raise ValueError("nar hash")
    if type(nar_size) is not int or not 0 < nar_size <= 16 * 1024**3:
        raise ValueError("nar size")


def decode(data):
    if not data or len(data) > MAX_BYTES:
        raise ValueError("size")
    return validate(json.loads(data, object_pairs_hook=unique))
