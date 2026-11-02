"""Fixed incident metadata archive. No data restore, secret read or new deploy.

Separate sealed copies replace OPERATION with probe/archive and, for archive,
BINDING with the exact closed probe result. No CLI argument selects an action.
An interrupted archive is retained and refuses an automatic second execution.
"""
import fcntl
import grp
import hashlib
import json
import os
from pathlib import Path
import pwd
import resource
import signal
import stat
import sys

PACKAGE = "/nix/store/irb47r5zxmffhlklmf2c613gdm8ydb1z-mrjam-first-release-controller-1"
sys.path.insert(0, PACKAGE + "/libexec")
from release_backend import Backend, Release, strict_json, PREVIOUS
from cutover import Phase
from system_control import GATE_NAME, ALLOWED

OPERATION = None
BINDING = None
OWNER = (0, 0)
STATE = Path("/var/lib/mrjam-cutover/first-deployment")
ARCHIVE = Path("/var/lib/mrjam-cutover/attempt-20261102-001")
VOLATILE = Path("/run/mrjam-cutover")
RUNTIME_ARCHIVE = Path("/run/mrjam-first-release-20261102-retained")
GUARD = Path("/run/systemd/system-generators/mrjam-first-cutover-guard")
RESULT = Path("/run/mrjam-first-release-status/result.json")
RELEASE_PATH = "/nix/store/rqfxds31bkc0wq2g69pp0nyhk2xgqfzp-mrjam-first-release-binding-1/release.json"
RELEASE_SHA256 = "e8626d9aca0e6a2760e9900f5b3233395ad310a09ea35b01af4b68b627511028"
REOPEN_RESULT_SHA256 = "2fd95f6ea3fa32c952e256edfc6cd4c1b59563b8ea5bf1957ae820f78b7b50c8"
FILES = ("initial.json", "adoption-started.json", "previous-resume-held-phase-20261102.json",
         "previous-resume-20261102.json", "previous-resume-opening-20261102.json", "phase.json")
# Only names and metadata are inspected. These files are never opened here.
RUNTIME = {
    "mrjam-admission-adoption": (947, 947, ("requests.sqlite", "mail.sqlite")),
    "mrjam-cycle-mail-adoption": (945, 945, ("mail.sqlite",)),
    "mrjam-archive-mail-adoption": (943, 943, ("closure.sqlite", "global.sqlite")),
    "mrjam-worker-credential-adaptation": (0, 0, ("proton-smtp.json", "cycle.json", "fermeture-hook.secret")),
}


class Refused(RuntimeError):
    pass


def require(value):
    if not value:
        raise Refused("FIRST_RELEASE_ARCHIVE_REFUSED")


def absent(path):
    return not path.exists() and not path.is_symlink()


def directory(path, mode=0o700):
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        for part in path.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
            os.close(fd)
            fd = child
            item = os.fstat(fd)
            require(item.st_uid in (0, OWNER[0]) and not item.st_mode & 0o022)
        item = os.fstat(fd)
        require((item.st_uid, item.st_gid) == OWNER and stat.S_IMODE(item.st_mode) == mode)
        return fd
    except BaseException:
        os.close(fd)
        raise


def identity(item):
    return {"device": item.st_dev, "inode": item.st_ino}


def read_metadata(path, maximum=65536):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and (before.st_uid, before.st_gid) == OWNER
                and before.st_nlink == 1 and stat.S_IMODE(before.st_mode) == 0o600)
        raw = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
    require(0 < len(raw) <= maximum and len(raw) == before.st_size
            and (before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
                (after.st_size, after.st_mtime_ns, after.st_ctime_ns))
    require(identity(path.lstat()) == identity(after))
    return raw, strict_json(raw, maximum)


def new_metadata(path, raw):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def sync(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def lock_state():
    folder = directory(STATE)
    try:
        fd = os.open("transaction.lock", os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=folder)
        try:
            item = os.fstat(fd)
            require(stat.S_ISREG(item.st_mode) and (item.st_uid, item.st_gid) == OWNER
                    and stat.S_IMODE(item.st_mode) == 0o600 and item.st_nlink == 1)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            require(identity(item) == identity((STATE / "transaction.lock").lstat()))
            return fd
        except BaseException:
            os.close(fd)
            raise
    finally:
        os.close(folder)


def runtime_inventory():
    result = {}
    for name, (uid, gid, names) in RUNTIME.items():
        path = RUNTIME_ARCHIVE.parent / name
        item = path.lstat()
        require(stat.S_ISDIR(item.st_mode) and (item.st_uid, item.st_gid) == (uid, gid)
                and stat.S_IMODE(item.st_mode) == 0o700 and set(os.listdir(path)) == set(names)
                and item.st_dev == RUNTIME_ARCHIVE.parent.stat().st_dev and not path.is_mount())
        for child in names:
            metadata = (path / child).lstat()
            require(stat.S_ISREG(metadata.st_mode) and metadata.st_uid == OWNER[0]
                    and metadata.st_gid == gid and metadata.st_nlink == 1
                    and stat.S_IMODE(metadata.st_mode) == 0o440 and 0 < metadata.st_size <=
                    (128 if child.endswith('.secret') else 65536 if name.endswith('credential-adaptation') else 64 * 1024**2))
        result[name] = identity(item)
    return result


def inventory(backend):
    require(absent(ARCHIVE) and absent(RUNTIME_ARCHIVE))
    require(set(os.listdir(STATE)) == set(FILES) | {"transaction.lock", "snapshot"})
    records = {}
    values = {}
    raws = {}
    for name in FILES:
        raw, value = read_metadata(STATE / name)
        records[name] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        values[name], raws[name] = value, raw
    backend.original = values["initial.json"]
    backend.validate_initial_record(backend.original)
    require(values["adoption-started.json"] == {"schema_version": 1, "release_sha256": RELEASE_SHA256})
    for name, phase in (("phase.json", Phase.RETURNED), ("previous-resume-held-phase-20261102.json", Phase.HELD)):
        value = values[name]
        require(type(value) is dict and set(value) == {"schema_version", "phase", "elapsed_seconds"}
                and type(value["schema_version"]) is int and value["schema_version"] == 1
                and value["phase"] == phase.value and type(value["elapsed_seconds"]) is int
                and value["elapsed_seconds"] >= 0)
    require(values["previous-resume-20261102.json"] == {"schema_version": 1, "release_sha256": RELEASE_SHA256,
            "incident": "first-release-20261102", "returned_observed_epoch": 1793648715, "restoration_authorized": False})
    require(values["previous-resume-opening-20261102.json"] == {"schema_version": 1, "release_sha256": RELEASE_SHA256,
            "phase": Phase.RETURNED.value, "private_http_verified": True})
    snapshot = STATE / "snapshot"
    fd = directory(snapshot)
    os.close(fd)
    require(set(os.listdir(snapshot)) == {"paired-state.tar", "paired-state.json", "candidate-state-retained"})
    for name in ("paired-state.tar", "paired-state.json"):
        item = (snapshot / name).lstat()
        require(stat.S_ISREG(item.st_mode) and (item.st_uid, item.st_gid) == OWNER
                and item.st_nlink == 1 and stat.S_IMODE(item.st_mode) == 0o600)
    fd = directory(snapshot / "candidate-state-retained")
    os.close(fd)
    require(set(os.listdir(VOLATILE)) == {"masks.json"})
    fd = directory(VOLATILE)
    os.close(fd)
    masks_raw, masks = read_metadata(VOLATILE / "masks.json")
    require(type(masks) is dict and set(masks) == {"schema_version", "units"}
            and type(masks["schema_version"]) is int and masks["schema_version"] == 1
            and type(masks["units"]) is list and all(type(x) is str for x in masks["units"])
            and masks["units"] == sorted(set(masks["units"]))
            and set(masks["units"]) <= set(backend.original["runtime_mask_intent"]))
    fd = directory(GUARD.parent, 0o755)
    os.close(fd)
    guard = GUARD.lstat()
    require(stat.S_ISLNK(guard.st_mode) and (guard.st_uid, guard.st_gid) == OWNER and guard.st_nlink == 1
            and os.readlink(GUARD) == backend.release.generator)
    result_raw, result = read_metadata(RESULT, 1024)
    require(result == {"schema_version": 1, "code": "COHERENT_RETURN_REQUIRES_RECOVERY", "phase": Phase.HELD.value})
    binding = {"schema_version": 1, "release_sha256": RELEASE_SHA256,
               "reopen_result_sha256": REOPEN_RESULT_SHA256, "records": records,
               "snapshot_identity": identity(snapshot.lstat()), "runtime_identities": runtime_inventory(),
               "masks_sha256": hashlib.sha256(masks_raw).hexdigest(), "guard_identity": identity(guard),
               "failed_result_sha256": hashlib.sha256(result_raw).hexdigest()}
    return binding, raws, masks_raw, result_raw, masks["units"]


def verify_live(backend, units):
    require(os.path.realpath("/run/current-system") == PREVIOUS
            and os.path.realpath("/nix/var/nix/profiles/system") == PREVIOUS)
    require(backend.control.execute([backend.release.tools["nft"], "list", "table", "inet", GATE_NAME], accepted=(0, 1)) == 1)
    for number in range(940, 949):
        for lookup in (pwd.getpwuid, grp.getgrgid):
            try:
                lookup(number)
            except KeyError:
                continue
            raise Refused("FIRST_RELEASE_ARCHIVE_REFUSED")
    for unit in units:
        value = backend.control.properties(unit)
        require(value["LoadState"] == "masked" and value["ActiveState"] in ("inactive", "failed")
                and int(value.get("MainPID", "0")) == 0)
    for unit in backend.original["foreign_masks"]:
        require(backend.control.properties(unit)["LoadState"] == "masked")
    require(backend.previous_http() == backend.original["http_status"])


def archive(backend, expected, lock):
    observed, raws, masks_raw, result_raw, units = inventory(backend)
    require(type(expected) is dict and observed == expected)
    require(STATE.stat().st_dev == ARCHIVE.parent.stat().st_dev)
    verify_live(backend, units)
    lock_identity = identity(os.fstat(lock))
    # Both archive destinations are exclusive. No old archive is overwritten or
    # treated as a cleanup target if a prior invocation was interrupted.
    ARCHIVE.mkdir(mode=0o700)
    RUNTIME_ARCHIVE.mkdir(mode=0o700)
    sync(ARCHIVE.parent)
    sync(RUNTIME_ARCHIVE.parent)
    intent = (json.dumps(expected, sort_keys=True, separators=(",", ":")) + "\n").encode()
    new_metadata(ARCHIVE / "archive-intent.json", intent)
    new_metadata(RUNTIME_ARCHIVE / "archive-intent.json", intent)
    new_metadata(ARCHIVE / "runtime-masks.json", masks_raw)
    new_metadata(ARCHIVE / "failed-controller-result.json", result_raw)
    new_metadata(ARCHIVE / "reopening-witness.json", (json.dumps({"schema_version": 1,
        "result_sha256": REOPEN_RESULT_SHA256, "code": "PREVIOUS_PUBLIC_REOPENED",
        "data_restored": False, "timers_pending": []}, sort_keys=True) + "\n").encode())
    sync(ARCHIVE)
    sync(RUNTIME_ARCHIVE)
    # Same-filesystem renames preserve all contents and identities. Never open
    # a staged SQLite image, credential file, retained candidate or tar archive.
    for name in sorted(RUNTIME):
        source = RUNTIME_ARCHIVE.parent / name
        require(identity(source.lstat()) == expected["runtime_identities"][name])
        os.rename(source, RUNTIME_ARCHIVE / name)
        sync(RUNTIME_ARCHIVE)
        sync(RUNTIME_ARCHIVE.parent)
    require(read_metadata(VOLATILE / "masks.json")[0] == masks_raw
            and identity(GUARD.lstat()) == expected["guard_identity"]
            and os.readlink(GUARD) == backend.release.generator)
    (VOLATILE / "masks.json").unlink()
    sync(VOLATILE)
    GUARD.unlink()
    sync(GUARD.parent)
    backend.control.execute([backend.release.tools["systemctl"], "daemon-reload"], timeout=60)
    for unit in units:
        value = backend.control.properties(unit)
        require(value["LoadState"] in ("loaded", "not-found") and value["ActiveState"] in ("inactive", "failed")
                and int(value.get("MainPID", "0")) == 0)
    for unit in backend.original["foreign_masks"]:
        require(backend.control.properties(unit)["LoadState"] == "masked")
    require(backend.previous_http() == backend.original["http_status"])
    require(backend.control.execute([backend.release.tools["nft"], "list", "table", "inet", GATE_NAME], accepted=(0, 1)) == 1)
    for name in FILES[:-1]:
        require(read_metadata(STATE / name)[0] == raws[name])
        os.rename(STATE / name, ARCHIVE / name)
        sync(ARCHIVE)
        sync(STATE)
    require(identity((STATE / "snapshot").lstat()) == expected["snapshot_identity"])
    os.rename(STATE / "snapshot", ARCHIVE / "snapshot")
    sync(ARCHIVE)
    sync(STATE)
    require(identity((STATE / "transaction.lock").lstat()) == lock_identity
            and set(os.listdir(STATE)) == {"transaction.lock", "phase.json"}
            and read_metadata(STATE / "phase.json")[0] == raws["phase.json"])
    # Commit last: a fresh deploy cannot pass while this terminal phase exists.
    os.rename(STATE / "phase.json", ARCHIVE / "phase.json")
    sync(ARCHIVE)
    sync(STATE)
    require(identity((STATE / "transaction.lock").lstat()) == lock_identity
            and set(os.listdir(STATE)) == {"transaction.lock"})
    new_metadata(ARCHIVE / "archive-complete.json", b'{"schema_version":1,"code":"FIRST_RELEASE_ATTEMPT_ARCHIVED"}\n')
    sync(ARCHIVE)
    return {"schema_version": 1, "code": "FIRST_RELEASE_ATTEMPT_ARCHIVED", "same_transaction_lock": True,
            "snapshot_restored": False, "application_data_modified": False, "secret_contents_read": False,
            "runtime_directories_retained": 4, "new_deployment_started": False}


def main():
    lock = None
    try:
        require(len(sys.argv) == 1 and OPERATION in ("probe", "archive")
                and (os.geteuid(), os.getegid()) == OWNER and os.uname().nodename == "srv1982677")
        os.umask(0o077)
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(Refused("FIRST_RELEASE_ARCHIVE_REFUSED")))
        signal.alarm(240)
        release = Release.immutable_file(RELEASE_PATH, RELEASE_SHA256)
        backend = Backend(release)
        lock = lock_state()
        if OPERATION == "probe":
            require(BINDING is None)
            binding, _raws, _masks_raw, _result_raw, units = inventory(backend)
            verify_live(backend, units)
            result = {"schema_version": 1, "code": "FIRST_RELEASE_ARCHIVE_READY", "binding": binding,
                      "reserved_identities_absent": True, "application_data_read": False,
                      "secret_contents_read": False, "mutation_performed": False}
        else:
            require(BINDING is not None)
            result = archive(backend, BINDING, lock)
    except BaseException:
        print('{"schema_version":1,"code":"FIRST_RELEASE_ARCHIVE_REFUSED"}')
        return 1
    finally:
        signal.alarm(0)
        if lock is not None:
            os.close(lock)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
