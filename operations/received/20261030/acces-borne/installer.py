"""Amorçage root limité, autorisé expressément le 30 octobre 2026.

Ne lit aucune clé privée, aucun journal ni contenu applicatif. N'active pas Nix.
Seuls un nouveau compte et ses fichiers d'accès dédiés sont créés.
RUNNER_SOURCE et PUBLIC_KEY sont fournis par le constructeur local vérifié.
"""
import base64
import fnmatch
import grp
import os
from pathlib import Path
import pwd
import re
import shutil
import stat
import subprocess
import sys


ROOT = Path("/var/lib/mrjam-inventory-access")
ACCOUNT = "mrjam-inventory"
OPERATION = "mrjam-inventory-v1"


def ssh_policy_allowed(text):
    values = {}
    for line in text.splitlines():
        fields = line.split(None, 1)
        if len(fields) != 2:
            continue
        key, value = fields[0].lower(), fields[1].strip()
        values.setdefault(key, []).append(value)
    one = lambda key: values.get(key, [""])[0]
    if one("pubkeyauthentication") != "yes" or one("usepam") != "yes":
        return False
    for key in ("authorizedkeyscommand", "trustedusercakeys", "forcecommand", "chrootdirectory"):
        if one(key) != "none":
            return False
    if one("authenticationmethods") not in ("any", "publickey"):
        return False
    paths = one("authorizedkeysfile").split()
    if not any(p in (".ssh/authorized_keys", "%h/.ssh/authorized_keys") for p in paths):
        return False
    allowed_paths = {".ssh/authorized_keys", "%h/.ssh/authorized_keys",
                     ".ssh/authorized_keys2", "%h/.ssh/authorized_keys2",
                     "/etc/ssh/authorized_keys.d/%u"}
    if set(paths) - allowed_paths:
        return False
    for key in ("allowusers", "allowgroups"):
        if key in values:
            patterns = " ".join(values[key]).split()
            if not any(fnmatch.fnmatchcase(ACCOUNT, p) for p in patterns):
                return False
    for key in ("denyusers", "denygroups"):
        if key in values:
            patterns = " ".join(values[key]).split()
            if any(fnmatch.fnmatchcase(ACCOUNT, p.split("@", 1)[0]) for p in patterns):
                return False
    # Only ordinary locale variables may be accepted at the SSH boundary.
    for pattern in " ".join(values.get("acceptenv", [])).split():
        if pattern not in ("LANG", "LC_*"):
            return False
    return True


def login_source(python):
    # -p suppresses BASH_ENV, exported functions and inherited shell options;
    # it does not grant any privilege and the script rejects UID/EUID zero.
    return f"""#!/run/current-system/sw/bin/bash -p
set +x
exec 2>/dev/null
[[ "$UID" -ne 0 && "$EUID" -ne 0 ]] || exit 64
[[ "$#" -eq 2 && "$1" == -c && "$2" == {OPERATION} ]] || exit 64
[[ "${{SSH_ORIGINAL_COMMAND-}}" == {OPERATION} ]] || exit 64
exec /run/current-system/sw/bin/env -i LANG=C LC_ALL=C \\
  '{python}' -I -S '{ROOT}/runner.py'
"""


def public_key_allowed(key):
    if not re.fullmatch(r"ssh-ed25519 [A-Za-z0-9+/=]+ mrjam-inventory-borne-20261030\n?", key):
        return False
    try:
        raw = base64.b64decode(key.split()[1], validate=True)
        return len(raw) == 51 and raw[:19] == b"\0\0\0\x0bssh-ed25519\0\0\0\x20"
    except Exception:
        return False


def effective_policy():
    parts = os.environ.get("SSH_CONNECTION", "").split()
    if len(parts) != 4 or not re.fullmatch(r"[0-9a-fA-F:.]+", parts[0] + parts[2]):
        return False
    if not parts[3].isdigit():
        return False
    criterion = f"user={ACCOUNT},addr={parts[0]},host={parts[0]},laddr={parts[2]},lport={parts[3]}"
    result = subprocess.run([shutil.which("sshd"), "-T", "-C", criterion],
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, timeout=10, check=False)
    return result.returncode == 0 and ssh_policy_allowed(result.stdout.decode("utf-8", "strict"))


def write_new(path, value, mode):
    with path.open("xb") as handle:
        handle.write(value.encode() if isinstance(value, str) else value)
    path.chmod(mode)


def install(runner_source, public_key):
    if os.getuid() != 0 or os.geteuid() != 0:
        return 40
    if sys.version_info < (3, 11):
        return 44
    if not public_key_allowed(public_key):
        return 45
    for lookup in (pwd.getpwnam, grp.getgrnam):
        try:
            lookup(ACCOUNT)
            return 42
        except KeyError:
            pass
    if ROOT.exists() or ROOT.is_symlink():
        return 42
    alternative_keys = Path("/etc/ssh/authorized_keys.d") / ACCOUNT
    if alternative_keys.exists() or alternative_keys.is_symlink():
        return 42
    if not effective_policy():
        return 46
    python = Path(sys.executable).resolve(strict=True)
    if not python.is_relative_to("/nix/store"):
        return 47
    # All components of the selected interpreter must remain root controlled.
    for part in (python, *python.parents):
        info = part.stat()
        sticky_store = part == Path("/nix/store") and info.st_mode & stat.S_ISVTX and not info.st_mode & 2
        if info.st_uid != 0 or (info.st_mode & 0o022 and not sticky_store):
            return 47
    for part in (ROOT.parent, *ROOT.parent.parents):
        info = part.stat()
        if info.st_uid != 0 or info.st_mode & 0o022:
            return 50
    os.umask(0o077)
    ROOT.mkdir(mode=0o755)
    # mkdir mode is affected by umask: set only permissions of these NEW paths.
    ROOT.chmod(0o755)
    (ROOT / "home").mkdir(mode=0o755)
    (ROOT / "home").chmod(0o755)
    (ROOT / "home/.ssh").mkdir(mode=0o755)
    (ROOT / "home/.ssh").chmod(0o755)
    write_new(ROOT / "runner.py", runner_source, 0o444)
    write_new(ROOT / "login", login_source(python), 0o555)
    # No authorized key is enabled until the account and all checks succeed.
    result = subprocess.run(
        [shutil.which("useradd"), "--system", "--user-group", "--no-create-home",
         "--home-dir", str(ROOT / "home"), "--shell", str(ROOT / "login"),
         "--password", "!", ACCOUNT],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        timeout=20, check=False,
    )
    if result.returncode:
        return 48
    user = pwd.getpwnam(ACCOUNT)
    if user.pw_uid == 0 or user.pw_gid == 0 or set(os.getgrouplist(ACCOUNT, user.pw_gid)) != {user.pw_gid}:
        return 49
    if not effective_policy():
        return 46
    (ROOT / "work").mkdir(mode=0o700)
    os.chown(ROOT / "work", user.pw_uid, user.pw_gid)
    for part in (ROOT, ROOT / "home", ROOT / "home/.ssh", ROOT / "runner.py", ROOT / "login"):
        info = part.lstat()
        if info.st_uid != 0 or info.st_mode & 0o022:
            return 50
    key_line = f'restrict,command="{OPERATION}" ' + public_key.strip() + "\n"
    write_new(ROOT / "home/.ssh/authorized_keys", key_line, 0o644)
    return 0


if __name__ == "__main__":
    try:
        status = install(RUNNER_SOURCE, PUBLIC_KEY)
    except Exception:
        status = 51
    raise SystemExit(status)
