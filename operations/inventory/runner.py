"""Fixed SSH operation; no executable or result is read from account-writable work.

Runtime configuration and the original three probe files live in this Nix store
package. The received V1 payload is an exact identity check, never executed.
No argument, command, path, environment selector or remote query is accepted.
"""
from __future__ import annotations

import ctypes
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import selectors
import shlex
import signal
import stat
import subprocess
import sys
import time


HERE = Path(__file__).resolve().parent
POLICY = json.loads((HERE / "policy.json").read_text())
RUNTIME = tuple((item["name"], item["bytes"], item["sha256"]) for item in POLICY["files"])
MAGIC = POLICY["magic"].encode("ascii")
INPUT_SIZE = len(MAGIC) + sum(size for _, size, _ in RUNTIME)
MAX_REPORT = POLICY["max_report_bytes"]
BUNDLE = HERE / "probe"
LOCK = Path(POLICY["lock"])


class Refused(Exception):
    def __init__(self, code: int):
        self.code = code


def unpack(data: bytes) -> None:
    """Verify the exact existing protocol; do not materialize received code."""
    if len(data) != INPUT_SIZE or not data.startswith(MAGIC):
        raise Refused(65)
    position = len(MAGIC)
    for _, size, digest in RUNTIME:
        if hashlib.sha256(data[position:position + size]).hexdigest() != digest:
            raise Refused(65)
        position += size


def trusted_bundle(bundle: Path) -> None:
    if not bundle.resolve().is_relative_to("/nix/store"):
        raise Refused(66)
    for component in (bundle, *bundle.parents):
        info = component.lstat()
        if info.st_uid != 0 or not stat.S_ISDIR(info.st_mode):
            raise Refused(66)
        sticky_store = component == Path("/nix/store") and bool(info.st_mode & stat.S_ISVTX) and not info.st_mode & 0o002
        if info.st_mode & 0o022 and not sticky_store:
            raise Refused(66)
    for name, size, digest in RUNTIME:
        source = bundle / name
        info = source.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise Refused(66)
        with source.open("rb") as handle:
            raw = handle.read(size + 1)
        if len(raw) != size or hashlib.sha256(raw).hexdigest() != digest:
            raise Refused(66)


def identity_allowed(config: dict) -> bool:
    uid, gid = config.get("uid"), config.get("gid")
    return (
        type(uid) is int and type(gid) is int and uid > 0 and gid > 0
        and os.getuid() == os.geteuid() == uid
        and os.getgid() == os.getegid() == gid
        and set(os.getgroups()) <= {gid}
    )


def apply_limits() -> None:
    limits = POLICY["limits"]
    for number, wanted in (
        (resource.RLIMIT_CORE, 0),
        (resource.RLIMIT_AS, limits["address_space_bytes"]),
        (resource.RLIMIT_CPU, limits["cpu_seconds"]),
        (resource.RLIMIT_FSIZE, limits["file_size_bytes"]),
        (resource.RLIMIT_NOFILE, limits["open_files"]),
        (resource.RLIMIT_NPROC, limits["processes"]),
    ):
        _, hard = resource.getrlimit(number)
        maximum = wanted if hard == resource.RLIM_INFINITY else min(wanted, hard)
        resource.setrlimit(number, (maximum, maximum))


def operation_lock(path: Path, gid: int) -> int:
    """Root-owned parent prevents the account from replacing the locked inode."""
    parent = path.parent.lstat()
    if not stat.S_ISDIR(parent.st_mode) or parent.st_uid != 0 or parent.st_mode & 0o022:
        raise Refused(75)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_gid != gid
                or stat.S_IMODE(info.st_mode) != 0o440 or info.st_nlink != 1 or info.st_size != 0):
            raise Refused(75)
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def interrupt(_signum, _frame) -> None:
    raise Refused(69)


def read_payload() -> bytes:
    signal.alarm(POLICY["max_input_seconds"])
    try:
        return sys.stdin.buffer.read(INPUT_SIZE + 1)
    finally:
        signal.alarm(0)


def pipeline_command(config: dict, bundle: Path) -> list[str]:
    # All paths are selected by immutable package configuration, not SSH input.
    python = shlex.quote(config["python"])
    probe = shlex.quote(str(bundle / "inventory.py"))
    validator = shlex.quote(str(bundle / "validate_report.py"))
    command = f"set -o pipefail\n{python} -I -S {probe} 2>/dev/null | {python} -I -S {validator} 2>/dev/null"
    return [config["bash"], "--noprofile", "--norc", "-p", "-c", command]


def child_ids() -> list[int]:
    """Linux fixed process metadata only; never a supplied path or PID."""
    me = os.getpid()
    try:
        with Path(f"/proc/self/task/{me}/children").open("rb") as handle:
            raw = handle.read(4097)
        if len(raw) > 4096:
            raise Refused(70)
        return [int(value) for value in raw.split()]
    except FileNotFoundError:
        # Some kernels omit CONFIG_CHECKPOINT_RESTORE and therefore children.
        # Read only bounded kernel process metadata, retain only direct PPids,
        # and never include process names, other fields or PIDs in any output.
        children = []
        with os.scandir("/proc") as entries:
            scanned = 0
            for item in entries:
                if not item.name.isascii() or not item.name.isdecimal():
                    continue
                scanned += 1
                if scanned > POLICY["max_proc_entries"]:
                    raise Refused(70)
                try:
                    with Path(f"/proc/{int(item.name)}/stat").open("rb") as handle:
                        raw = handle.read(4097)
                except ProcessLookupError:
                    continue
                except FileNotFoundError:
                    continue
                if len(raw) > 4096:
                    raise Refused(70)
                # comm can contain spaces, newlines and parentheses; fields
                # after its last ')' contain state followed by numeric PPid.
                fields = raw.rsplit(b") ", 1)[-1].split()
                if len(fields) < 2:
                    raise Refused(70)
                if int(fields[1]) == me:
                    children.append(int(item.name))
        return children


def enable_subreaper() -> None:
    # The immutable original probe starts its own sessions. PR_SET_CHILD_SUBREAPER
    # ensures those descendants come back to this process when their parent dies,
    # including after setsid(); killing the outer process group alone is not enough.
    if child_ids():
        raise Refused(70)
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
        raise Refused(70)
    enabled = ctypes.c_int()
    if libc.prctl(37, ctypes.byref(enabled), 0, 0, 0) != 0 or enabled.value != 1:
        raise Refused(70)


def cleanup_children(process: subprocess.Popen) -> None:
    """Kill and reap the entire adopted tree before any report may be emitted."""
    handled = (signal.SIGALRM, signal.SIGTERM, signal.SIGINT, signal.SIGHUP)
    previous = {number: signal.signal(number, signal.SIG_IGN) for number in handled}
    try:
        # The unreaped leader reserves the PID until after group cleanup.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        if process.stdout is not None:
            process.stdout.close()
        deadline = time.monotonic() + 2
        while True:
            # Direct children include orphans adopted from killed descendants;
            # repeat to handle deeper trees and a fork racing with SIGKILL.
            for child in child_ids():
                try:
                    os.kill(child, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            while True:
                try:
                    pid, status = os.waitpid(-1, os.WNOHANG)
                except ChildProcessError:
                    break
                if not pid:
                    break
                if pid == process.pid:
                    process.returncode = os.waitstatus_to_exitcode(status)
            if not child_ids():
                return
            if time.monotonic() >= deadline:
                # A kernel task stuck in uninterruptible sleep cannot be promised
                # dead. Fail closed, never certify success or return a report.
                raise Refused(69)
            time.sleep(0.005)
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


def run_pipeline(command: list[str], timeout: float, cap: int = MAX_REPORT) -> bytes:
    """Bound output/runtime; kill and reap groups and detached descendants.

    This internal function is exercised with synthetic commands by the tests;
    the public entry point only constructs the immutable pipeline above.
    """
    process = None
    try:
        enable_subreaper()
        process = subprocess.Popen(
            command, cwd="/", stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, env={"LANG": "C", "LC_ALL": "C"},
            close_fds=True, start_new_session=True,
        )
        output = bytearray()
        deadline = time.monotonic() + timeout
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise Refused(69)
                for key, _ in selector.select(remaining):
                    chunk = os.read(key.fd, cap + 1)
                    if not chunk:
                        selector.unregister(key.fd)
                        break
                    output.extend(chunk)
                    if len(output) > cap:
                        raise Refused(68)
            while True:
                outcome = os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
                if outcome is not None:
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise Refused(69)
                time.sleep(min(0.01, remaining))
        if outcome.si_code != os.CLD_EXITED or outcome.si_status != 0:
            raise Refused(67)
        if not output:
            raise Refused(68)
        return bytes(output)
    finally:
        if process is not None:
            cleanup_children(process)


def validated_report(raw: bytes, bundle: Path) -> bytes:
    spec = importlib.util.spec_from_file_location("mrjam_fixed_report_filter", bundle / "validate_report.py")
    if spec is None or spec.loader is None:
        raise Refused(68)
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    try:
        report = validator.validate(raw, (bundle / "inventory.schema.json").read_bytes())
        if report.get("status") == "error":
            raise Refused(68)
    except Exception:
        raise Refused(68) from None
    return (json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def main() -> int:
    descriptor = None
    try:
        if len(sys.argv) != 1 or os.getuid() == 0 or os.geteuid() == 0:
            return 64
        config = json.loads((HERE / "runtime.json").read_text())
        if not identity_allowed(config):
            return 64
        os.umask(0o077)
        for signum in (signal.SIGALRM, signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            signal.signal(signum, interrupt)
        apply_limits()
        trusted_bundle(BUNDLE)
        descriptor = operation_lock(LOCK, config["gid"])
        unpack(read_payload())
        raw = run_pipeline(pipeline_command(config, BUNDLE), POLICY["max_run_seconds"])
        report = validated_report(raw, BUNDLE)
        sys.stdout.buffer.write(report)
        sys.stdout.buffer.flush()
        return 0
    except Refused as error:
        return error.code
    except BlockingIOError:
        return 75
    except Exception:
        return 70
    finally:
        if descriptor is not None:
            os.close(descriptor)


if __name__ == "__main__":
    raise SystemExit(main())
