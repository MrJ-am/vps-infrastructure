#!/usr/bin/env python3
"""One bounded validation request: exactly a source-manifest SHA256 on stdin.

The trusted Nix configuration selects the validator and its closure. Candidate
input cannot select programs, dependency roots, environment, network or mounts.
Only root-owned read-only staged code is accepted. No token or signer is present.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import resource
import select
import signal
import stat
import struct
import subprocess
import sys
import tempfile
import threading
import time

POLICY = Path("/etc/mrjam-validation-worker/policy.json")
INPUT_ROOT = Path("/var/lib/mrjam-validation-input")
LOCK = Path("/run/mrjam-validation-worker/operation.lock")
STORE = re.compile(r"/nix/store/[0-9a-z]{32}-[A-Za-z0-9+._?=-]{1,180}")
HEX = re.compile(r"[0-9a-f]{64}")
MAX_FILES = 20000
MAX_INPUT = 1024 * 1024 * 1024
MAX_MANIFEST = 4 * 1024 * 1024
ARTIFACTS = (("server", 64 * 1024 * 1024), ("frontend.tar", 64 * 1024 * 1024), ("verification.json", 65536))
# Linux fcntl ABI; some Python builds omit the symbolic constants. Operations
# still execute and fail closed if the kernel does not implement sealing.
F_ADD_SEALS = 1033
F_GET_SEALS = 1034
SEALS = 0x01 | 0x02 | 0x04 | 0x08


class Refused(Exception):
    pass


def require(value, code):
    if not value:
        raise Refused(code)


def _pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, "DUPLICATE_KEY")
        result[key] = value
    return result


def exact(value, fields):
    require(type(value) is dict and set(value) == set(fields), "INVALID_FIELDS")


def parse(raw):
    try:
        return json.loads(raw, object_pairs_hook=_pairs, parse_constant=lambda _: (_ for _ in ()).throw(Refused("INVALID_NUMBER")))
    except Refused:
        raise
    except Exception:
        raise Refused("INVALID_JSON") from None


def root_readonly(path, *, directory=False, owner=0):
    info = os.lstat(path)
    require((stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)) and info.st_uid == owner and not info.st_mode & 0o222, "UNTRUSTED_INPUT")
    if not directory:
        require(info.st_nlink == 1, "UNTRUSTED_INPUT")
    return info


def checked_bytes(path, limit, *, owner=0):
    before = root_readonly(path, owner=owner)
    require(before.st_size <= limit, "INPUT_LIMIT")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        opened = os.fstat(stream.fileno())
        require((opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns) == (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns), "INPUT_CHANGED")
        data = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
        require(len(data) == before.st_size and (after.st_size, after.st_mtime_ns, after.st_ctime_ns) == (before.st_size, before.st_mtime_ns, before.st_ctime_ns), "INPUT_CHANGED")
        return data


def policy(value):
    exact(value, ("schema_version", "rules_revision", "validator_store", "bubblewrap_store", "closure_file"))
    require(type(value["schema_version"]) is int and value["schema_version"] == 1, "INVALID_VERSION")
    require(type(value["rules_revision"]) is str and re.fullmatch(r"[0-9a-f]{40}", value["rules_revision"]), "INVALID_RULES")
    for field in ("validator_store", "bubblewrap_store"):
        require(type(value[field]) is str and STORE.fullmatch(value[field]), "INVALID_STORE_PATH")
    require(type(value["closure_file"]) is str and value["closure_file"].endswith("/store-paths") and STORE.fullmatch(value["closure_file"].removesuffix("/store-paths")), "INVALID_CLOSURE")
    return value


def closure(raw, validator):
    require(len(raw) <= 262144, "CLOSURE_LIMIT")
    try:
        paths = raw.decode("ascii").splitlines()
    except Exception:
        raise Refused("INVALID_CLOSURE") from None
    require(0 < len(paths) <= 1024 and len(paths) == len(set(paths)) and validator in paths, "INVALID_CLOSURE")
    require(all(STORE.fullmatch(path) for path in paths), "INVALID_CLOSURE")
    return sorted(paths)


def verify_input(root, proposal, rules_revision, *, owner=0):
    require(type(proposal) is str and HEX.fullmatch(proposal), "INVALID_PROPOSAL")
    root_readonly(root, directory=True, owner=owner)
    source = root / proposal
    root_readonly(source, directory=True, owner=owner)
    raw = checked_bytes(source / "manifest.json", MAX_MANIFEST, owner=owner)
    require(hashlib.sha256(raw).hexdigest() == proposal, "MANIFEST_MISMATCH")
    manifest = parse(raw)
    exact(manifest, ("schema_version", "rules_revision", "files"))
    require(type(manifest["schema_version"]) is int and manifest["schema_version"] == 1 and manifest["rules_revision"] == rules_revision, "RULES_MISMATCH")
    files = manifest["files"]
    require(type(files) is list and 0 < len(files) <= MAX_FILES, "FILE_LIMIT")
    declared = {"manifest.json"}
    directories = set()
    total = 0
    for entry in files:
        exact(entry, ("path", "bytes", "sha256"))
        name = entry["path"]
        require(type(name) is str and re.fullmatch(r"[A-Za-z0-9._+~/-]{1,300}", name) and not name.startswith("/") and str(PurePosixPath(name)) == name and all(part not in (".", "..") for part in PurePosixPath(name).parts), "INVALID_PATH")
        require(name not in declared, "DUPLICATE_PATH")
        declared.add(name)
        require(type(entry["bytes"]) is int and 0 <= entry["bytes"] <= MAX_INPUT and type(entry["sha256"]) is str and HEX.fullmatch(entry["sha256"]), "INVALID_FILE")
        total += entry["bytes"]
        require(total <= MAX_INPUT, "INPUT_LIMIT")
        for relative in PurePosixPath(name).parents:
            if str(relative) != ".":
                root_readonly(source / str(relative), directory=True, owner=owner)
                directories.add(str(relative))
        target = source / name
        before = root_readonly(target, owner=owner)
        require(before.st_size == entry["bytes"], "FILE_SIZE_MISMATCH")
        fd = os.open(target, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            opened = os.fstat(stream.fileno())
            require((opened.st_dev, opened.st_ino, opened.st_ctime_ns) == (before.st_dev, before.st_ino, before.st_ctime_ns), "INPUT_CHANGED")
            hashed = hashlib.sha256()
            count = 0
            while block := stream.read(1024 * 1024):
                count += len(block)
                require(count <= entry["bytes"], "INPUT_CHANGED")
                hashed.update(block)
            after = os.fstat(stream.fileno())
            require((before.st_size, before.st_mtime_ns, before.st_ctime_ns) == (after.st_size, after.st_mtime_ns, after.st_ctime_ns) and count == before.st_size, "INPUT_CHANGED")
        require(hashed.hexdigest() == entry["sha256"], "FILE_HASH_MISMATCH")
    # Reject hidden extras, sockets, symlinks and undeclared empty directories.
    seen = set()
    count = 0
    for base, subdirs, filenames in os.walk(source, followlinks=False):
        count += len(subdirs) + len(filenames)
        require(count <= MAX_FILES * 2, "FILE_LIMIT")
        for name in subdirs:
            target = Path(base) / name
            relative = str(target.relative_to(source))
            require(relative in directories, "UNDECLARED_INPUT")
            root_readonly(target, directory=True, owner=owner)
        for name in filenames:
            target = Path(base) / name
            relative = str(target.relative_to(source))
            require(relative in declared, "UNDECLARED_INPUT")
            root_readonly(target, owner=owner)
            seen.add(relative)
    require(seen == declared, "INPUT_INCOMPLETE")
    return source


def command(configuration, paths, source, *, channel=None, seccomp=None):
    policy(configuration)
    require(str(source) == str(INPUT_ROOT / source.name) and HEX.fullmatch(source.name), "INVALID_SOURCE_ROOT")
    # Only the independently pinned supervisor runs in this outer namespace.
    # It must put every candidate command in an inner user/PID/mount namespace;
    # inner namespaces disable further userns creation after setup.
    arguments = [configuration["bubblewrap_store"] + "/bin/bwrap", "--unshare-all", "--unshare-user", "--die-with-parent", "--new-session", "--cap-drop", "ALL", "--clearenv",
                 "--dir", "/nix", "--dir", "/nix/store", "--dir", "/etc", "--proc", "/proc", "--dev", "/dev",
                 "--size", "268435456", "--tmpfs", "/tmp", "--size", "1073741824", "--tmpfs", "/work",
                 "--ro-bind", str(source), "/input", "--chdir", "/work", "--setenv", "HOME", "/work", "--setenv", "LANG", "C.UTF-8"]
    for path in paths:
        require(STORE.fullmatch(path), "INVALID_CLOSURE")
        arguments.extend(("--ro-bind", path, path))
    if seccomp is not None:
        arguments.extend(("--seccomp", str(seccomp)))
    if channel is not None:
        arguments.extend(("--size", "268435456", "--tmpfs", "/output", "--bind", str(channel), "/output/channel"))
    arguments.extend((configuration["validator_store"] + "/bin/mrjam-validate", "/input"))
    return arguments


def execute(arguments, *, timeout=1800, pass_fds=(), cancel=None):
    def limits():
        os.setsid()
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_FSIZE, (1073741824, 1073741824))
        resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
        resource.setrlimit(resource.RLIMIT_NPROC, (256, 256))
        resource.setrlimit(resource.RLIMIT_CPU, (1800, 1800))
    process = subprocess.Popen(arguments, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               env={}, close_fds=True, pass_fds=pass_fds, preexec_fn=limits)
    try:
        deadline = time.monotonic() + timeout
        while True:
            if cancel is not None and cancel.is_set():
                raise Refused("ARTIFACT_STREAM_INVALID")
            remaining = deadline - time.monotonic()
            require(remaining > 0, "VALIDATION_TIMEOUT")
            try:
                return process.wait(timeout=min(0.25, remaining)) == 0
            except subprocess.TimeoutExpired:
                continue
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)


def seccomp_filter():
    require(os.uname().machine == "x86_64", "UNQUALIFIED_ARCHITECTURE")
    # AUDIT_ARCH_X86_64 only; no x32 compat ABI. EPERM for debugger, cross-process
    # memory/fd access and kernel observation/instrumentation. The filter is
    # inherited by the nested candidate namespaces, with no capability to lift it.
    instructions = [(0x20, 0, 0, 4), (0x15, 1, 0, 0xC000003E), (0x06, 0, 0, 0x80000000),
                    (0x20, 0, 0, 0), (0x35, 0, 1, 0x40000000), (0x06, 0, 0, 0x00050001)]
    for number in (101, 298, 310, 311, 312, 321, 438):
        instructions.extend(((0x15, 0, 1, number), (0x06, 0, 0, 0x00050001)))
    instructions.append((0x06, 0, 0, 0x7FFF0000))
    raw = b"".join(struct.pack("<HBBI", *instruction) for instruction in instructions)
    fd = os.memfd_create("mrjam-validation-seccomp", os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
    os.write(fd, raw)
    os.lseek(fd, 0, os.SEEK_SET)
    fcntl.fcntl(fd, F_ADD_SEALS, SEALS)
    return fd


def seal_artifacts(outputs):
    require(set(outputs) == {name for name, _ in ARTIFACTS}, "INVALID_OUTPUT_FDS")
    result = []
    for name, limit in ARTIFACTS:
        fd = outputs[name]
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and 0 < info.st_size <= limit, "ARTIFACT_LIMIT")
        fcntl.fcntl(fd, F_ADD_SEALS, SEALS)
        os.lseek(fd, 0, os.SEEK_SET)
        hashed = hashlib.sha256()
        while block := os.read(fd, 65536):
            hashed.update(block)
        os.lseek(fd, 0, os.SEEK_SET)
        result.append({"name": name, "bytes": info.st_size, "sha256": hashed.hexdigest()})
    return result


def collect_channel(reader, outputs, finished):
    header = bytearray()
    records = None
    index = 0
    remaining = 0
    hashed = None
    while True:
        ready, _, _ = select.select([reader], [], [], 0.1)
        if not ready:
            continue
        block = os.read(reader, 65536)
        if not block:
            require(finished.is_set(), "CHANNEL_CLOSED_EARLY")
            require(records is not None and index == len(ARTIFACTS), "ARTIFACTS_INCOMPLETE")
            return records
        if records is None:
            before, separator, rest = block.partition(b"\n")
            header.extend(before)
            require(len(header) <= 4096, "ARTIFACT_HEADER_LIMIT")
            if not separator:
                continue
            value = parse(bytes(header))
            exact(value, ("artifacts",))
            records = value["artifacts"]
            require(type(records) is list and len(records) == len(ARTIFACTS), "INVALID_ARTIFACT_HEADER")
            for record, (name, limit) in zip(records, ARTIFACTS):
                exact(record, ("name", "bytes", "sha256"))
                require(record["name"] == name and type(record["bytes"]) is int and 0 < record["bytes"] <= limit and type(record["sha256"]) is str and HEX.fullmatch(record["sha256"]), "INVALID_ARTIFACT_HEADER")
            remaining = records[0]["bytes"]
            hashed = hashlib.sha256()
            block = rest
        while block:
            require(index < len(ARTIFACTS), "EXTRA_ARTIFACT_DATA")
            selected = block[:remaining]
            written = os.write(outputs[ARTIFACTS[index][0]], selected)
            require(written == len(selected), "ARTIFACT_STORAGE_FAILED")
            hashed.update(selected)
            remaining -= len(selected)
            block = block[len(selected):]
            if remaining == 0:
                require(hashed.hexdigest() == records[index]["sha256"], "ARTIFACT_HASH_MISMATCH")
                index += 1
                if index < len(ARTIFACTS):
                    remaining = records[index]["bytes"]
                    hashed = hashlib.sha256()


def run_with_artifacts(make_command, outputs, *, timeout=1800):
    # Named FIFO binding is supported by Bubblewrap; anonymous memfds cannot
    # be bind-mounted through --bind-fd. The host alone owns receiving memfds.
    with tempfile.TemporaryDirectory(prefix="mrjam-validation-channel-") as temporary:
        fifo = Path(temporary) / "artifacts"
        os.mkfifo(fifo, 0o600)
        reader = os.open(fifo, os.O_RDONLY | os.O_NONBLOCK)
        holder = os.open(fifo, os.O_WRONLY | os.O_NONBLOCK)
        seccomp = seccomp_filter()
        finished = threading.Event()
        invalid = threading.Event()
        outcome = []
        def collect():
            try:
                outcome.append(collect_channel(reader, outputs, finished))
            except Exception:
                outcome.append(None)
                invalid.set()
        thread = threading.Thread(target=collect, daemon=True)
        thread.start()
        success = False
        try:
            success = execute(make_command(fifo, seccomp), timeout=timeout, pass_fds=(seccomp,), cancel=invalid)
        finally:
            finished.set()
            os.close(holder)
            thread.join(timeout=5)
            os.close(reader)
            os.close(seccomp)
        require(not thread.is_alive(), "COLLECTOR_TIMEOUT")
        if success:
            require(len(outcome) == 1 and outcome[0] is not None, "ARTIFACTS_INCOMPLETE")
        return success


def request_digest():
    deadline = time.monotonic() + 5
    data = b""
    while len(data) < 65:
        remaining = deadline - time.monotonic()
        require(remaining > 0, "INPUT_TIMEOUT")
        ready, _, _ = select.select([0], [], [], remaining)
        require(ready, "INPUT_TIMEOUT")
        block = os.read(0, 66 - len(data))
        require(block, "INVALID_PROPOSAL")
        data += block
    require(len(data) == 65 and data[-1:] == b"\n", "INVALID_PROPOSAL")
    try:
        value = data[:-1].decode("ascii")
    except Exception:
        raise Refused("INVALID_PROPOSAL") from None
    require(HEX.fullmatch(value), "INVALID_PROPOSAL")
    # A single frame only, with EOF; no shell-like streaming protocol.
    remaining = deadline - time.monotonic()
    require(remaining > 0, "INPUT_TIMEOUT")
    ready, _, _ = select.select([0], [], [], remaining)
    require(ready and os.read(0, 1) == b"", "EXTRA_INPUT")
    return value


def main():
    outputs = {}
    try:
        require(len(sys.argv) == 1 and os.getuid() != 0, "INVALID_INVOCATION")
        proposal = request_digest()
        configuration = policy(parse(checked_bytes(POLICY, 16384)))
        paths = closure(checked_bytes(Path(configuration["closure_file"]), 262144), configuration["validator_store"])
        lock = os.open(LOCK, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(lock, "rb") as stream:
            info = os.fstat(stream.fileno())
            require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and info.st_nlink == 1 and stat.S_IMODE(info.st_mode) == 0o440, "UNSAFE_LOCK")
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise Refused("BUSY") from None
            source = verify_input(INPUT_ROOT, proposal, configuration["rules_revision"])
            outputs = {name: os.memfd_create("mrjam-" + name, os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING) for name, _ in ARTIFACTS}
            success = run_with_artifacts(lambda channel, seccomp: command(configuration, paths, source, channel=channel, seccomp=seccomp), outputs)
            artifacts = seal_artifacts(outputs) if success else []
        receipt = {"schema_version": 1, "decision": "passed" if success else "failed", "proposal_sha256": proposal,
                   "rules_revision": configuration["rules_revision"], "artifacts": artifacts, "authority": "local-controller-receipt"}
        sys.stdout.buffer.write(json.dumps(receipt, separators=(",", ":")).encode("ascii") + b"\n")
        if success:
            for name, _ in ARTIFACTS:
                while block := os.read(outputs[name], 65536):
                    sys.stdout.buffer.write(block)
        sys.stdout.buffer.flush()
        return 0 if success else 1
    except Refused as error:
        print(json.dumps({"decision": "reject", "code": str(error)}, separators=(",", ":")))
        return 2
    except Exception:
        print('{"decision":"reject","code":"WORKER_FAILED"}')
        return 2
    finally:
        for fd in outputs.values():
            os.close(fd)


if __name__ == "__main__":
    raise SystemExit(main())
