#!/usr/bin/env python3
"""Fixed, read-only NixOS metadata inventory. Run locally, never as an agent RPC.

Python 3.11+; standard library only. Invoke with -I -S and no arguments.
No file, command, service or query can be supplied through its public interface.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import sys
import time
from typing import NamedTuple


SCHEMA_VERSION = 1
BIN = Path("/run/current-system/sw/bin")
STORE = Path("/nix/store")
MAX_OUTPUT_BYTES = 2048
COMMAND_TIMEOUT_SECONDS = 3.0
MAX_UNSIGNED = (1 << 63) - 1


class VersionProbe(NamedTuple):
    program: str
    arguments: tuple[str, ...]
    prefix: bytes


# Numeric release cores only. Build flags, commit labels and suffixes never leave
# the host. Missing executables are unknown, not evidence of absent services.
VERSION_PROBES = {
    "nixos": VersionProbe("nixos-version", ("--short",), b""),
    "nix": VersionProbe("nix", ("--version",), rb"nix \(Nix\) "),
    "forgejo": VersionProbe("forgejo", ("--version",), rb"Forgejo version "),
    "forgejo_runner": VersionProbe("forgejo-runner", ("--version",), rb"forgejo-runner version v?"),
    "postgresql": VersionProbe("postgres", ("--version",), rb"postgres \(PostgreSQL\) "),
    "kanidm": VersionProbe("kanidmd", ("--version",), rb"kanidmd "),
}

# Unit names are policy, not user input. A differently named service is unknown.
SERVICE_UNITS = {
    "forgejo": "forgejo.service",
    "postgresql": "postgresql.service",
    "kanidm": "kanidm.service",
    "nginx": "nginx.service",
    "mrjam_metier": "mrjam-metier.service",
    "nextcloud_php_pool": "phpfpm-nextcloud.service",
}
SERVICE_STATES = frozenset({"active", "reloading", "inactive", "failed", "activating", "deactivating", "maintenance", "refreshing"})
LOAD_STATES = frozenset({"stub", "loaded", "not-found", "bad-setting", "error", "merged", "masked"})
ERROR_CODES = frozenset({"UNAVAILABLE", "UNTRUSTED_EXECUTABLE", "COMMAND_FAILED", "TIMEOUT", "OUTPUT_LIMIT", "INVALID_OUTPUT", "UNSUPPORTED_ARGUMENTS", "INTERNAL_ERROR"})


def failure(code: str) -> dict[str, str]:
    return {"status": "unknown", "code": code if code in ERROR_CODES else "INTERNAL_ERROR"}


def numeric(value: object) -> dict[str, object]:
    if type(value) is int and 0 <= value <= MAX_UNSIGNED:
        return {"status": "ok", "value": value}
    return failure("INVALID_OUTPUT")


def trusted_executable(program: str) -> tuple[str | None, str | None]:
    """Accept only fixed NixOS system binaries resolving into a trusted store.

    The writable sticky store root is allowed; individual store entries and all
    other path components must be root-owned and not group/world writable.
    """
    if program not in {x.program for x in VERSION_PROBES.values()} | {"systemctl"}:
        return None, "UNTRUSTED_EXECUTABLE"
    source = BIN / program
    try:
        resolved = source.resolve(strict=True)
        if not resolved.is_relative_to(STORE):
            return None, "UNTRUSTED_EXECUTABLE"
        for component in (source, *source.parents, resolved, *resolved.parents):
            entry = component.lstat()
            if entry.st_uid != 0:
                return None, "UNTRUSTED_EXECUTABLE"
            if stat.S_ISLNK(entry.st_mode):
                continue
            writable = entry.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
            sticky_store = component == STORE and bool(entry.st_mode & stat.S_ISVTX) and not (entry.st_mode & stat.S_IWOTH)
            if writable and not sticky_store:
                return None, "UNTRUSTED_EXECUTABLE"
        entry = resolved.stat()
        if not stat.S_ISREG(entry.st_mode) or not (entry.st_mode & stat.S_IXUSR):
            return None, "UNTRUSTED_EXECUTABLE"
        return str(resolved), None
    except FileNotFoundError:
        return None, "UNAVAILABLE"
    except (OSError, RuntimeError):
        return None, "UNTRUSTED_EXECUTABLE"


def _fixed_command(program: str, arguments: tuple[str, ...]) -> tuple[bytes | None, str | None]:
    """Internal runner. Its only callers use the constant tables above.

    Discard stderr before capture; cap stdout and runtime. No shell, inherited
    environment, stdin, configuration, command-line override or network call.
    """
    permitted = {(x.program, x.arguments) for x in VERSION_PROBES.values()}
    permitted.update(("systemctl", service_arguments(unit)) for unit in SERVICE_UNITS.values())
    if (program, arguments) not in permitted:
        return None, "UNTRUSTED_EXECUTABLE"
    executable, error = trusted_executable(program)
    if error:
        return None, error
    process = None
    try:
        process = subprocess.Popen(
            [executable, *arguments],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env={"PATH": str(BIN), "LANG": "C", "LC_ALL": "C", "SYSTEMD_COLORS": "0", "SYSTEMD_PAGER": ""},
            cwd="/",
            shell=False,
            close_fds=True,
            start_new_session=True,
        )
        output = bytearray()
        deadline = time.monotonic() + COMMAND_TIMEOUT_SECONDS
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None, "TIMEOUT"
                for key, _ in selector.select(remaining):
                    chunk = os.read(key.fd, MAX_OUTPUT_BYTES + 1)
                    if not chunk:
                        selector.unregister(key.fd)
                        break
                    output.extend(chunk)
                    if len(output) > MAX_OUTPUT_BYTES:
                        return None, "OUTPUT_LIMIT"
            # Observe exit without reaping: the leader's PID must stay allocated
            # until the private process group has been terminated in finally.
            while True:
                outcome = os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
                if outcome is not None:
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None, "TIMEOUT"
                time.sleep(min(0.01, remaining))
        if outcome.si_code != os.CLD_EXITED or outcome.si_status != 0:
            return None, "COMMAND_FAILED"
        return bytes(output), None
    except (OSError, ValueError):
        return None, "COMMAND_FAILED"
    finally:
        if process is not None:
            # Always terminate the subprocess group: a descendant could outlive
            # its parent after closing stdout. Only this private group is used.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            if process.stdout is not None:
                process.stdout.close()
            try:
                process.wait(timeout=1)
            except (subprocess.TimeoutExpired, OSError):
                pass


def version_result(probe: VersionProbe, raw: bytes | None, error: str | None) -> dict[str, object]:
    if error or raw is None:
        return failure(error or "INVALID_OUTPUT")
    if len(raw) > MAX_OUTPUT_BYTES:
        return failure("OUTPUT_LIMIT")
    # No extracted string is emitted: only bounded integers and fixed literals.
    match = re.match(rb"\A" + probe.prefix + rb"([0-9]{1,4}(?:\.[0-9]{1,4}){1,3})(?=[\s+\-]|$)", raw)
    if not match:
        return failure("INVALID_OUTPUT")
    return {"status": "ok", "release_core": [int(x) for x in match.group(1).split(b".")], "exact_build": "not_reported"}


def service_arguments(unit: str) -> tuple[str, ...]:
    return ("show", "--property=LoadState", "--property=ActiveState", "--", unit)


def service_result(raw: bytes | None, error: str | None) -> dict[str, str]:
    if error or raw is None:
        return failure(error or "INVALID_OUTPUT")
    for load in LOAD_STATES:
        for active in SERVICE_STATES:
            lines = (f"LoadState={load}", f"ActiveState={active}")
            expected = ("\n".join(lines) + "\n").encode()
            reversed_expected = ("\n".join(reversed(lines)) + "\n").encode()
            if raw in (expected, reversed_expected):
                return {"status": "ok", "load_state": load, "active_state": active}
    return failure("INVALID_OUTPUT")


def fixed_kernel_flag(path: Path) -> dict[str, object]:
    """Two fixed numeric kernel controls; no caller-provided path is accepted."""
    if path not in {Path("/proc/sys/user/max_user_namespaces"), Path("/proc/sys/kernel/unprivileged_userns_clone")}:
        return failure("UNAVAILABLE")
    try:
        with path.open("rb") as handle:
            raw = handle.read(33)
        if not re.fullmatch(rb"[0-9]{1,19}\n?", raw):
            return failure("INVALID_OUTPUT")
        return {"status": "ok", "enabled": int(raw) > 0}
    except OSError:
        return failure("UNAVAILABLE")


def collect() -> dict[str, object]:
    resources: dict[str, object] = {"logical_cpu_count": numeric(os.cpu_count())}
    try:
        pages, page_size = os.sysconf("SC_PHYS_PAGES"), os.sysconf("SC_PAGE_SIZE")
        resources["memory_total_bytes"] = numeric(pages * page_size if pages > 0 and page_size > 0 else None)
    except (OSError, ValueError):
        resources["memory_total_bytes"] = failure("UNAVAILABLE")
    try:
        disk = os.statvfs("/")
        resources["root_filesystem_total_bytes"] = numeric(disk.f_blocks * disk.f_frsize)
        resources["root_filesystem_available_bytes"] = numeric(disk.f_bavail * disk.f_frsize)
    except OSError:
        resources["root_filesystem_total_bytes"] = failure("UNAVAILABLE")
        resources["root_filesystem_available_bytes"] = failure("UNAVAILABLE")
    try:
        kvm = Path("/dev/kvm").stat()
        kvm_result: dict[str, object] = {"status": "ok", "device_present": stat.S_ISCHR(kvm.st_mode)}
    except FileNotFoundError:
        kvm_result = {"status": "ok", "device_present": False}
    except OSError:
        kvm_result = failure("UNAVAILABLE")
    return {
        "schema_version": SCHEMA_VERSION,
        "scope": "local_read_only_metadata",
        "authority": "unverified_observation",
        "resources": resources,
        "isolation": {
            "kvm": kvm_result,
            "user_namespace_limit_nonzero": fixed_kernel_flag(Path("/proc/sys/user/max_user_namespaces")),
            "unprivileged_user_namespace_switch": fixed_kernel_flag(Path("/proc/sys/kernel/unprivileged_userns_clone")),
        },
        "versions": {key: version_result(probe, *_fixed_command(probe.program, probe.arguments)) for key, probe in VERSION_PROBES.items()},
        "services": {key: service_result(*_fixed_command("systemctl", service_arguments(unit))) for key, unit in SERVICE_UNITS.items()},
    }


def main() -> int:
    if len(sys.argv) != 1:
        print(json.dumps({"schema_version": SCHEMA_VERSION, "status": "error", "code": "UNSUPPORTED_ARGUMENTS"}))
        return 2
    try:
        report = collect()
    except Exception:
        # Exceptions must not disclose file paths, environment values, or stderr.
        print(json.dumps({"schema_version": SCHEMA_VERSION, "status": "error", "code": "INTERNAL_ERROR"}))
        return 1
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
