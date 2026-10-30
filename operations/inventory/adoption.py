"""Read-only preflight of the one existing account and fixed filesystem boundary.

Run before any activation through an authorized administrative channel. It
neither creates accounts nor changes permissions, keys, shells or services.
No arbitrary path/account, secret, shadow file or application content is read.
"""
import grp
import json
import os
from pathlib import Path
import pwd
import re
import stat
import sys


HERE = Path(__file__).resolve().parent
ACCOUNT = "mrjam-inventory"
ROOT = Path("/var/lib/mrjam-inventory-access")
KEYS = Path("/etc/ssh/mrjam-inventory-authorized-keys")
LOCKDIR = Path("/run/mrjam-inventory-lock")


def entry(path, uid, gid=None, directory=False, mode=None):
    value = path.lstat()
    if (not (stat.S_ISDIR(value.st_mode) if directory else stat.S_ISREG(value.st_mode))
            or value.st_uid != uid or (gid is not None and value.st_gid != gid)
            or (mode is not None and stat.S_IMODE(value.st_mode) != mode)):
        return False
    return not value.st_mode & 0o022 if uid == 0 else True


def bounded_read(path, maximum):
    with path.open("rb") as handle:
        value = handle.read(maximum + 1)
    if len(value) > maximum:
        raise ValueError("BOUND_EXCEEDED")
    return value


def legacy_login(text):
    # Accept only the exact old entry program, with its pinned store interpreter.
    match = re.search(r"'(/nix/store/[0-9a-df-np-sv-z]{32}-[A-Za-z0-9+._=-]+/bin/python3(?:\.[0-9]+)?)' -I -S", text)
    if not match:
        return False
    python = match.group(1)
    expected = f'''#!/run/current-system/sw/bin/bash -p
set +x
exec 2>/dev/null
[[ "$UID" -ne 0 && "$EUID" -ne 0 ]] || exit 64
[[ "$#" -eq 2 && "$1" == -c && "$2" == mrjam-inventory-v1 ]] || exit 64
[[ "${{SSH_ORIGINAL_COMMAND-}}" == mrjam-inventory-v1 ]] || exit 64
exec /run/current-system/sw/bin/env -i LANG=C LC_ALL=C \\
  '{python}' -I -S '/var/lib/mrjam-inventory-access/runner.py'
'''
    return text == expected


def check(config):
    uid, gid = config.get("uid"), config.get("gid")
    if type(uid) is not int or type(gid) is not int or uid <= 0 or gid <= 0:
        return False
    user, group = pwd.getpwnam(ACCOUNT), grp.getgrnam(ACCOUNT)
    if (user.pw_uid != uid or user.pw_gid != gid or group.gr_gid != gid
            or user.pw_dir != str(ROOT / "home") or set(os.getgrouplist(ACCOUNT, gid)) != {gid}
            or not set(group.gr_mem) <= {ACCOUNT}):
        return False
    for path in (ROOT, ROOT / "home", ROOT / "home/.ssh"):
        if not entry(path, 0, 0, directory=True, mode=0o755):
            return False
    if not entry(ROOT / "work", uid, gid, directory=True, mode=0o700):
        return False
    if not entry(ROOT / "login", 0, 0, mode=0o555) or not entry(ROOT / "runner.py", 0, 0, mode=0o444):
        return False
    if not legacy_login(bounded_read(ROOT / "login", 2048).decode("utf-8")):
        return False
    # The old runner bytes are a supplied code artifact, never application data.
    import hashlib
    if hashlib.sha256(bounded_read(ROOT / "runner.py", 3420)).hexdigest() != config["legacyRunnerSha256"]:
        return False
    expected = "".join('restrict,command="mrjam-inventory-v1" ' + key + "\n" for key in config["publicKeys"])
    old_keys = ROOT / "home/.ssh/authorized_keys"
    if not entry(old_keys, 0, 0, mode=0o644) or bounded_read(old_keys, 4096).decode("utf-8") != expected:
        return False
    if user.pw_shell not in (str(ROOT / "login"), str(HERE.parent / "bin/mrjam-inventory-login")):
        return False
    # Refuse to overwrite an unrelated declaration at the new key location.
    if KEYS.exists() or KEYS.is_symlink():
        if not entry(KEYS.parent, 0, 0, directory=True):
            return False
        resolved = KEYS.resolve(strict=True)
        if KEYS.is_symlink() and not resolved.is_relative_to("/nix/store"):
            return False
        if not entry(resolved, 0, 0, mode=0o444) or resolved.lstat().st_nlink != 1 or bounded_read(resolved, 4096).decode("utf-8") != expected:
            return False
    # /run may be absent before adoption/after boot. Never let tmpfiles silently
    # repair an unrelated object or switch a symlink to the managed boundary.
    if LOCKDIR.exists() or LOCKDIR.is_symlink():
        if not entry(LOCKDIR, 0, gid, directory=True, mode=0o750):
            return False
        lock = LOCKDIR / "operation.lock"
        if lock.exists() or lock.is_symlink():
            if not entry(lock, 0, gid, mode=0o440):
                return False
            info = lock.lstat()
            if info.st_nlink != 1 or info.st_size != 0:
                return False
    return True


def main():
    if len(sys.argv) != 1:
        print('{"status":"refused","code":"UNSUPPORTED_ARGUMENTS"}')
        return 64
    try:
        okay = check(json.loads((HERE / "runtime.json").read_text()))
    except Exception:
        okay = False
    print(json.dumps({"status": "ok" if okay else "refused", "code": "ADOPTION_STATE_MATCHES" if okay else "ADOPTION_STATE_MISMATCH"}, separators=(",", ":")))
    return 0 if okay else 1


if __name__ == "__main__":
    raise SystemExit(main())
