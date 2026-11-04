"""Read only the fixed controller003 failure record and checkpoint.

No log, application file, credential, pending publication or arbitrary path is
read. The immutable backend supplies its exact closed schema vocabularies.
"""
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import stat
import sys

CONTROLLER = "/nix/store/aclk4gzc77q0g4mjp6r1i18l06a6ks4w-mrjam-first-release-controller-1"
BACKEND_SHA256 = "cd1d81ce8dab252c423c5850d7362c941d2d4816858a549263cd03559f674b6c"
RELEASE_SHA256 = "9fd41d93000fb058397fa49db73d4e0e0c45bb4888fa3ec6a52c148f8ec83341"
STATE = Path("/var/lib/mrjam-cutover/first-deployment")
OWNER = (0, 0)
HOST = "srv1982677"


class Refused(RuntimeError):
    pass


def require(value):
    if not value:
        raise Refused()


def fingerprint(item):
    return (item.st_dev, item.st_ino, item.st_mode, item.st_uid, item.st_gid,
            item.st_nlink, item.st_size, item.st_mtime_ns, item.st_ctime_ns)


def load_contract():
    path = Path(CONTROLLER) / "libexec/release_backend.py"
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    with os.fdopen(fd, "rb") as stream:
        item = os.fstat(stream.fileno())
        require(stat.S_ISREG(item.st_mode) and item.st_uid == item.st_gid == 0
                and not item.st_mode & 0o222 and item.st_size <= 128 * 1024)
        raw = stream.read(128 * 1024 + 1)
    require(hashlib.sha256(raw).hexdigest() == BACKEND_SHA256)
    sys.dont_write_bytecode = True
    sys.path.insert(0, CONTROLLER + "/libexec")
    import release_backend
    require(Path(release_backend.__file__) == path)
    return release_backend


def open_state():
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        for part in STATE.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                            dir_fd=fd)
            os.close(fd)
            fd = child
            item = os.fstat(fd)
            require(item.st_uid in (0, OWNER[0]) and not item.st_mode & 0o022)
        item = os.fstat(fd)
        require((item.st_uid, item.st_gid) == OWNER and stat.S_IMODE(item.st_mode) == 0o700)
        return fd
    except BaseException:
        os.close(fd)
        raise


def read_document(directory, name, maximum, contract):
    require(name in ("failure.json", "phase.json"))
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC,
                     dir_fd=directory)
    except FileNotFoundError:
        return None
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and (before.st_uid, before.st_gid) == OWNER
                and stat.S_IMODE(before.st_mode) == 0o600 and before.st_nlink == 1
                and 0 < before.st_size <= maximum)
        raw = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
    current = os.stat(name, dir_fd=directory, follow_symlinks=False)
    require(len(raw) == before.st_size <= maximum
            and fingerprint(before) == fingerprint(after) == fingerprint(current))
    value = contract.strict_json(raw, maximum)
    require(type(value) is dict)
    return value


def observe(contract):
    directory = open_state()
    try:
        failure = read_document(directory, "failure.json", 1024, contract)
        phase_document = read_document(directory, "phase.json", 4096, contract)
    finally:
        os.close(directory)
    if failure is not None:
        require(type(failure) is dict and set(failure) == {
            "schema_version", "release_sha256", "step", "component", "code"})
        require(type(failure["schema_version"]) is int and failure["schema_version"] == 1
                and type(failure["release_sha256"]) is str
                and failure["release_sha256"] == RELEASE_SHA256)
        for key, allowed in (("step", contract.FAILURE_STEPS),
                             ("component", contract.FAILURE_COMPONENTS),
                             ("code", contract.FAILURE_CODES)):
            require(type(failure[key]) is str and failure[key] in allowed)
    phase = "absent"
    if phase_document is not None:
        require(type(phase_document) is dict
                and set(phase_document) == {"schema_version", "phase", "elapsed_seconds"})
        require(type(phase_document["schema_version"]) is int and phase_document["schema_version"] == 1
                and type(phase_document["elapsed_seconds"]) is int
                and phase_document["elapsed_seconds"] >= 0
                and type(phase_document["phase"]) is str
                and phase_document["phase"] in {value.value for value in contract.Phase})
        phase = phase_document["phase"]
    return {"schema_version": 1, "code": "FIRST_RELEASE_FAILURE_OBSERVED",
            "release_sha256": RELEASE_SHA256, "failure_present": failure is not None,
            "failure": failure, "phase": phase}


def deadline(_number, _frame):
    raise Refused()


def main():
    try:
        require(len(sys.argv) == 1 and os.geteuid() == 0 and os.uname().nodename == HOST)
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        signal.signal(signal.SIGALRM, deadline)
        signal.alarm(15)
        value = observe(load_contract())
        print(json.dumps(value, sort_keys=True, separators=(",", ":")))
        return 0
    except BaseException:
        print('{"schema_version":1,"code":"FIRST_RELEASE_FAILURE_OBSERVATION_REFUSED"}')
        return 1
    finally:
        signal.alarm(0)


if __name__ == "__main__":
    raise SystemExit(main())
