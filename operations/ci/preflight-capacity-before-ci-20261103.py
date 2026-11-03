"""Fixed read-only CI capacity metadata, gated on successful release005.

No identity enumeration, application content, command line, journal or secret.
Only fixed technical names/UIDs, kernel counters and selected unit properties.
"""
import grp
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import resource
import selectors
import signal
import stat
import subprocess
import sys
import time

CONTROLLER = "/nix/store/aclk4gzc77q0g4mjp6r1i18l06a6ks4w-mrjam-first-release-controller-1"
BACKEND_SHA256 = "cd1d81ce8dab252c423c5850d7362c941d2d4816858a549263cd03559f674b6c"
RELEASE_SHA256 = "9fd41d93000fb058397fa49db73d4e0e0c45bb4888fa3ec6a52c148f8ec83341"
PROMOTED = "/nix/store/phi68cwg38madbq8p805yvrsyry8g8wr-nixos-system-srv1982677-26.05pre-git"
SYSTEMCTL = "/nix/store/0xiinbh7pbj479i5v28mqnjrvhvbdibf-systemd-260.2/bin/systemctl"
CONTROLLER_UNIT = "mrjam-first-release-20261102-05.service"
RESULT = Path("/run/mrjam-first-release-status-05/result.json")
STATE = Path("/var/lib/mrjam-cutover/first-deployment")
CGROUP_ROOT = Path("/sys/fs/cgroup")
ACCOUNTS = ("mrjam-forgejo-registration", "mrjam-forgejo-runner",
            "mrjam-validation-worker", "mrjam-validation-collector", "mrjam-forgejo-policy",
            "mrjam-validation-authority")
GROUPS = ACCOUNTS + ("mrjam-validation-submitters", "mrjam-validation-requesters")
UNITS = tuple(name + ".service" for name in (
    "forgejo", "postgresql", "nginx", "kanidm", "phpfpm-nextcloud", "redis-nextcloud",
    "vision-embeddings", "mrjam-rust-blue", "mrjam-rust-green", "mrjam-identity",
    "mrjam-identity-deletion", "mrjam-vision-admission", "mrjam-vision-closure",
    "mrjam-vision-cycle", "mrjam-vision-archive", "mrjam-vision-replay"))
# Exact qualified dc09 unit Slice= settings; hyphens define slice ancestry.
# Matheval and courriel execute inside the Rust slot, not separate services.
CGROUP_PATHS = {unit: "/system.slice/" + unit for unit in UNITS}
CGROUP_PATHS.update({
    "mrjam-rust-blue.service": "/mrjam.slice/mrjam-rust.slice/mrjam-rust-blue.service",
    "mrjam-rust-green.service": "/mrjam.slice/mrjam-rust.slice/mrjam-rust-green.service",
    "phpfpm-nextcloud.service": "/system.slice/system-phpfpm.slice/phpfpm-nextcloud.service",
})
PROPERTIES = ("Id", "LoadState", "ActiveState", "SubState", "MainPID", "ExecMainCode",
              "ExecMainStatus", "ControlGroup", "MemoryMax", "MemoryHigh", "MemorySwapMax",
              "TasksMax", "CPUWeight")
CGROUP_FILES = ("memory.current", "memory.peak", "memory.max", "memory.high",
                "memory.swap.current", "memory.swap.max", "memory.events",
                "pids.current", "pids.max", "cpu.max", "cpu.stat", "cpu.weight")


class Refused(RuntimeError):
    pass


def require(value):
    if not value:
        raise Refused()


def public_read(path, maximum):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        require(stat.S_ISREG(os.fstat(fd).st_mode))
        raw = os.read(fd, maximum + 1)
        require(0 < len(raw) <= maximum)
        return raw.decode("ascii", "strict").strip()
    finally:
        os.close(fd)


def contract():
    path = Path(CONTROLLER) / "libexec/release_backend.py"
    require(hashlib.sha256(path.read_bytes()).hexdigest() == BACKEND_SHA256)
    sys.dont_write_bytecode = True
    sys.path.insert(0, CONTROLLER + "/libexec")
    import release_backend
    require(Path(release_backend.__file__) == path)
    return release_backend


def number(value, *, limit=False, unavailable=False):
    require(type(value) is str)
    if limit and value in ("max", "infinity", "18446744073709551615"):
        return "max"
    if unavailable and value in ("", "[not set]"):
        return None
    require(re.fullmatch(r"[0-9]{1,20}", value) is not None)
    result = int(value)
    require(result <= 2**64 - 1)
    return result


def show_units():
    args = [SYSTEMCTL, "show", "--no-pager", "--property=" + ",".join(PROPERTIES),
            CONTROLLER_UNIT, *UNITS]
    process = None
    try:
        process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, start_new_session=True,
                                   env={"LANG": "C", "LC_ALL": "C", "PATH": "/run/current-system/sw/bin"})
        until = time.monotonic() + 10
        raw = bytearray()
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while True:
                left = until - time.monotonic()
                require(left > 0 and selector.select(left))
                block = os.read(process.stdout.fileno(), 4096)
                if not block:
                    break
                raw.extend(block)
                require(len(raw) <= 65536)
        require(process.wait(timeout=max(0.01, until - time.monotonic())) == 0)
        return parse_units(raw.decode("ascii", "strict"))
    finally:
        if process is not None:
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=1)
            process.stdout.close()


def parse_units(raw):
    result = {}
    for block in raw.strip().split("\n\n"):
        row = {}
        for line in block.splitlines():
            key, separator, value = line.partition("=")
            require(separator and key in PROPERTIES and key not in row)
            row[key] = value
        require(set(("Id", "LoadState", "ActiveState", "SubState", "MainPID",
                     "ExecMainCode", "ExecMainStatus")) <= set(row))
        name = row["Id"]
        require(name in (CONTROLLER_UNIT, *UNITS) and name not in result)
        require(row["LoadState"] in ("loaded", "not-found", "error", "masked", "bad-setting"))
        require(row["ActiveState"] in ("active", "inactive", "activating", "deactivating",
                                       "failed", "reloading", "maintenance"))
        for key in ("MainPID", "ExecMainCode", "ExecMainStatus"):
            number(row[key])
        result[name] = row
    require(set(result) == set((CONTROLLER_UNIT, *UNITS)))
    return result


def successful_release(backend, units):
    require(os.path.realpath("/run/current-system") == PROMOTED
            and os.path.realpath("/nix/var/nix/profiles/system") == PROMOTED)
    backend.private_directory(RESULT.parent)
    result = backend.private_read(RESULT, 1024)
    require(type(result) is dict and type(result.get("schema_version")) is int
            and result == {"schema_version": 1, "code": "CUTOVER_VERIFIED", "phase": backend.Phase.OPEN.value})
    require(backend.Checkpoint(STATE).read() == backend.Phase.OPEN)
    row = units[CONTROLLER_UNIT]
    require({key: row[key] for key in ("LoadState", "ActiveState", "SubState", "MainPID",
                                     "ExecMainCode", "ExecMainStatus")} == {
        "LoadState": "loaded", "ActiveState": "active", "SubState": "exited",
        "MainPID": "0", "ExecMainCode": "1", "ExecMainStatus": "0"})


def identities():
    reserves = {}
    for value in range(949, 960):
        row = {}
        for key, lookup in (("uid_free", pwd.getpwuid), ("gid_free", grp.getgrgid)):
            try:
                lookup(value)
            except KeyError:
                row[key] = True
            else:
                row[key] = False
        reserves[str(value)] = row
    accounts = {}
    for name in ACCOUNTS:
        try:
            item = pwd.getpwnam(name)
        except KeyError:
            accounts[name] = {"present": False}
        else:
            accounts[name] = {"present": True, "uid": item.pw_uid, "gid": item.pw_gid}
    groups = {}
    for name in GROUPS:
        try:
            item = grp.getgrnam(name)
        except KeyError:
            groups[name] = {"present": False}
        else:
            groups[name] = {"present": True, "gid": item.gr_gid}
    return {"reserved_ids": reserves, "technical_accounts": accounts, "technical_groups": groups}


def memory(raw):
    wanted = {"MemTotal", "MemAvailable", "SwapTotal", "SwapFree"}
    result = {}
    for line in raw.splitlines():
        key, _, value = line.partition(":")
        if key in wanted:
            require(key + "_bytes" not in result)
            match = re.fullmatch(r"\s*([0-9]{1,20}) kB\s*", value)
            require(match is not None)
            result[key + "_bytes"] = number(match.group(1)) * 1024
    require(set(result) == {name + "_bytes" for name in wanted})
    require(result["MemAvailable_bytes"] <= result["MemTotal_bytes"]
            and result["SwapFree_bytes"] <= result["SwapTotal_bytes"])
    return result


def selected_counters(raw, required, optional=()):
    values = {}
    for line in raw.splitlines():
        fields = line.split()
        require(len(fields) == 2 and re.fullmatch(r"[a-z_]+(?:\.[a-z_]+)*", fields[0]) and fields[0] not in values)
        values[fields[0]] = number(fields[1])
    require(set(required) <= set(values))
    return {name: values[name] for name in (*required, *optional) if name in values}


def cgroup(unit, row):
    require(unit in UNITS)
    desired = CGROUP_PATHS[unit]
    # Never follow a path supplied by PID1; open only the fixed expected path.
    if row.get("ControlGroup", "") != desired:
        return {"observed": False, "reason": "absent" if not row.get("ControlGroup") else "unexpected-location"}
    root = CGROUP_ROOT / desired.lstrip("/")
    try:
        require(stat.S_ISDIR(root.lstat().st_mode))
        raw = {name: public_read(root / name, 4096) for name in CGROUP_FILES}
    except FileNotFoundError:
        return {"observed": False, "reason": "not-available-or-ended"}
    values = {name: number(raw[name], limit=name in ("memory.max", "memory.high", "memory.swap.max", "pids.max")) for name in CGROUP_FILES
              if name not in ("cpu.max", "cpu.stat", "memory.events")}
    cpu = raw["cpu.max"].split()
    require(len(cpu) == 2)
    values["cpu.max"] = {"quota_usec": number(cpu[0], limit=True), "period_usec": number(cpu[1])}
    require(values["cpu.max"]["period_usec"] > 0)
    values["cpu.stat"] = selected_counters(raw["cpu.stat"], ("usage_usec", "user_usec", "system_usec"),
                                           ("nr_periods", "nr_throttled", "throttled_usec", "nr_bursts", "burst_usec"))
    values["memory.events"] = selected_counters(raw["memory.events"], ("low", "high", "max", "oom", "oom_kill"),
                                                ("oom_group_kill",))
    return {"observed": True, "counters_and_limits": values}


def observe(backend, units):
    successful_release(backend, units)
    result = {"schema_version": 1, "code": "CI_CAPACITY_METADATA_OBSERVED",
              "release_sha256": RELEASE_SHA256, "promoted_generation_matches": True,
              "identity_metadata": identities(), "memory": memory(public_read("/proc/meminfo", 65536)),
              "disk": {}, "services": {}}
    for path in ("/nix/store", "/var/lib"):
        item = os.statvfs(path)
        result["disk"][path] = {"available_bytes": item.f_bavail * item.f_frsize,
                                "total_bytes": item.f_blocks * item.f_frsize,
                                "available_inodes": item.f_favail}
    result["disk"]["same_filesystem"] = os.stat("/nix/store").st_dev == os.stat("/var/lib").st_dev
    for name in UNITS:
        row = units[name]
        result["services"][name] = {"load_state": row["LoadState"], "active_state": row["ActiveState"],
            "declared_limits": {key: number(row.get(key, ""), limit=True, unavailable=True)
                                for key in ("MemoryMax", "MemoryHigh", "MemorySwapMax", "TasksMax", "CPUWeight")},
            "cgroup": cgroup(name, row)}
    # Recheck the terminal binding after collecting observations, without locks.
    successful_release(backend, units)
    result["capacity_or_ci_activation_authorized"] = False
    return result


def main():
    try:
        require(len(sys.argv) == 1 and os.geteuid() == os.getegid() == 0
                and os.uname().nodename == "srv1982677")
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(Refused()))
        signal.alarm(45)
        backend = contract()
        value = observe(backend, show_units())
        print(json.dumps(value, sort_keys=True, separators=(",", ":")))
        return 0
    except BaseException:
        print('{"schema_version":1,"code":"CI_CAPACITY_METADATA_REFUSED"}')
        return 1
    finally:
        signal.alarm(0)


if __name__ == "__main__":
    raise SystemExit(main())
