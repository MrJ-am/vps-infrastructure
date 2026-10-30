"""Filter an effective sshd policy provided by the administrative executor.

This validator runs no command, opens no network and never prints its input.
It is a required preflight, not a substitute for actual refused SSH requests.
"""
import json
import re
import sys


ACCOUNT = "mrjam-inventory"
REQUIRED = {
    "pubkeyauthentication": "yes",
    "authenticationmethods": "publickey",
    "passwordauthentication": "no",
    "kbdinteractiveauthentication": "no",
    "permitemptypasswords": "no",
    "hostbasedauthentication": "no",
    "authorizedkeysfile": "/etc/ssh/mrjam-inventory-authorized-keys",
    "authorizedkeyscommand": "none",
    "authorizedprincipalsfile": "none",
    "authorizedprincipalscommand": "none",
    "trustedusercakeys": "none",
    "forcecommand": "mrjam-inventory-v1",
    "chrootdirectory": "none",
    "disableforwarding": "yes",
    "allowagentforwarding": "no",
    "allowtcpforwarding": "no",
    "allowstreamlocalforwarding": "no",
    "permitopen": "none",
    "permitlisten": "none",
    "permittunnel": "no",
    "permittty": "no",
    "permituserrc": "no",
    "permituserenvironment": "no",
    "x11forwarding": "no",
    "maxsessions": "1",
}
OPTIONAL_REQUIRED = {"gssapiauthentication": "no"}


def allowed(raw):
    if not isinstance(raw, bytes) or len(raw) > 65536:
        return False
    try:
        observed = {}
        for line in raw.decode("utf-8", "strict").splitlines():
            parts = line.split(None, 1)
            if len(parts) != 2:
                return False
            key, value = parts[0].lower(), parts[1].strip()
            if key in (REQUIRED.keys() | OPTIONAL_REQUIRED.keys()) and key in observed:
                return False
            observed.setdefault(key, []).append(value)
        if any(observed.get(key) != [expected] for key, expected in REQUIRED.items()):
            return False
        # Some OpenSSH builds omit this field. Absence proves no capability
        # fact; AuthenticationMethods=publickey plus PubkeyAuthentication=yes
        # above are the mandatory control that excludes every other method.
        if any(key in observed and observed[key] != [expected] for key, expected in OPTIONAL_REQUIRED.items()):
            return False
        for key in ("allowusers", "allowgroups", "denyusers", "denygroups"):
            values = " ".join(observed.get(key, [])).split()
            # Fail closed on patterns/negations/host qualifiers. This validator
            # does not pretend Python glob syntax implements OpenSSH matching.
            if any(not re.fullmatch(r"[A-Za-z0-9._-]+", value) for value in values):
                return False
            if key.startswith("allow") and key in observed and ACCOUNT not in values:
                return False
            if key.startswith("deny") and ACCOUNT in values:
                return False
        for pattern in " ".join(observed.get("acceptenv", [])).split():
            if pattern not in ("LANG", "LC_*"):
                return False
        return True
    except Exception:
        return False


def main():
    if len(sys.argv) != 1:
        print('{"status":"refused","code":"UNSUPPORTED_ARGUMENTS"}')
        return 64
    try:
        okay = allowed(sys.stdin.buffer.read(65537))
    except Exception:
        okay = False
    print(json.dumps({"status": "ok" if okay else "refused", "code": "SSH_POLICY_MATCHES" if okay else "SSH_POLICY_MISMATCH"}, separators=(",", ":")))
    return 0 if okay else 1


if __name__ == "__main__":
    raise SystemExit(main())
