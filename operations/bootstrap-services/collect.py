"""Fixed service/identity metadata only; no argv, environment, data or log read.

The human-launched immutable supervisor confines this process. CAP_SYS_PTRACE
permits readlink of the seven selected processes' exe links; ptrace and memory
access syscalls are not allowed by its system-call policy. No PID is accepted.
"""
import json
import os
from pathlib import Path
import pwd
import sys

ROOT = Path(__file__).absolute().parent
sys.path.insert(0, str(ROOT))
from bounded import Refused, run
from contract import ACCOUNTS, UNITS, STORE, EXECUTABLE, validate

ENVIRONMENT = {"LANG": "C", "LC_ALL": "C", "PATH": "/no-path", "HOME": "/nonexistent",
    "DBUS_SYSTEM_BUS_ADDRESS": "unix:path=/run/dbus/system_bus_socket",
    "SYSTEMD_LOG_LEVEL": "emerg", "SYSTEMD_COLORS": "0", "NIX_USER_CONF_FILES": "/dev/null",
    "NIX_REMOTE": "daemon"}


def account(name):
    result = {"state": "unknown", "uid": None, "gid": None}
    try:
        entry = pwd.getpwnam(name)
        if 1 <= entry.pw_uid < 2**31 and 1 <= entry.pw_gid < 2**31:
            result.update(state="observed", uid=entry.pw_uid, gid=entry.pw_gid)
    except KeyError:
        result["state"] = "absent"
    except (OSError, ValueError, OverflowError):
        pass
    return result


def nar(runtime, path):
    result = {"store_path": path, "nar_hash": None, "nar_size": None}
    if path is None:
        return result
    try:
        raw = run([runtime["nix"], "--extra-experimental-features", "nix-command", "path-info",
                   "--offline", "--json", "--json-format", "1", path], environment=ENVIRONMENT, seconds=10, limit=32768)
        data = json.loads(raw)
        if type(data) is dict and set(data) == {path}:
            entry = data[path]
        elif type(data) is list and len(data) == 1 and data[0].get("path") == path:
            entry = data[0]
        else:
            raise ValueError("shape")
        candidate = dict(result, nar_hash=entry["narHash"], nar_size=entry["narSize"])
        from contract import metadata
        metadata(candidate, exact=True)
        result = candidate
    except (Refused, OSError, ValueError, KeyError, TypeError):
        pass
    return result


def status(runtime, name):
    raw = run([runtime["systemctl"], "--system", "show", "--property=LoadState,ActiveState,MainPID",
               name + ".service"], environment=ENVIRONMENT, seconds=5, limit=256)
    pairs = [line.split("=", 1) for line in raw.decode("ascii").splitlines()]
    if len(pairs) != 3 or {x[0] for x in pairs} != {"LoadState", "ActiveState", "MainPID"}:
        raise ValueError("shape")
    values = dict(pairs)
    if values["LoadState"] == "not-found":
        return "absent", None
    if values["LoadState"] != "loaded":
        return "unknown", None
    state = values["ActiveState"]
    if state not in ("active", "inactive", "failed"):
        return "unknown", None
    pid = values["MainPID"]
    if not pid.isascii() or not pid.isdigit() or len(pid) > 10:
        raise ValueError("pid")
    return state, int(pid)


def service(runtime, name):
    result = {"state": "unknown", "executable": None, **nar(runtime, None)}
    try:
        state, pid = status(runtime, name)
        result["state"] = state
        if state != "active" or pid is None or not 1 <= pid <= 2**31 - 1:
            return result
        # readlink only; never open cmdline, environ, fd, mem, maps or a log.
        executable = os.readlink("/proc/" + str(pid) + "/exe")
        if EXECUTABLE.fullmatch(executable) is None or "/../" in executable or "/./" in executable:
            return result
        if status(runtime, name) != (state, pid) or os.readlink("/proc/" + str(pid) + "/exe") != executable:
            return result
        store = "/".join(executable.split("/")[:4])
        result.update(nar(runtime, store), executable=executable)
    except (Refused, OSError, ValueError, TypeError):
        pass
    return result


def main():
    try:
        if len(sys.argv) != 1 or os.geteuid() != 0:
            raise Refused()
        runtime = json.loads((ROOT / "runtime.json").read_text())
        current = os.readlink("/run/current-system")
        generation = nar(runtime, current if STORE.fullmatch(current) else None)
        report = {"schema_version": 1, "authority": "unverified_observation", "generation": generation,
                  "accounts": {name: account(name) for name in ACCOUNTS},
                  "services": {name: service(runtime, name) for name in UNITS}}
        sys.stdout.buffer.write(validate(report))
        return 0
    except Exception:
        return 65


if __name__ == "__main__":
    raise SystemExit(main())
