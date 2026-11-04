"""Retain one exact old infrastructure bundle before the next sealed receipt.

No arguments, Git operations, deletion, publication or application changes.
Only the fixed old bundle is opened, as opaque bytes for its SHA-256 check.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import stat
import sys

OWNER = (0, 0)
PREVIOUS = "/nix/store/jn9rf2fgk2y6dbhdnjwkmfww3pchkyb9-nixos-system-nixos-26.05.8639.c5c4a43b0e80"
STATE = Path("/var/lib/mrjam-cutover/first-deployment")
SOURCE = Path("/var/lib/mrjam-source-import")
ARCHIVE = "previous-12d1beb-20261102"
BUNDLE = "vps-infrastructure.bundle"
BYTES = 3954624601
SHA256 = "69e6625c3288972d91fe77175fa021ba3ef229fc035c457cd1fc4619425a2bbc"


class Refused(RuntimeError):
    pass


def require(value):
    if not value:
        raise Refused("PREVIOUS_INFRASTRUCTURE_RETENTION_REFUSED")


def directory(path):
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        for part in path.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
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


def regular(item, size=None):
    require(stat.S_ISREG(item.st_mode) and (item.st_uid, item.st_gid) == OWNER
            and stat.S_IMODE(item.st_mode) == 0o600 and item.st_nlink == 1)
    if size is not None:
        require(item.st_size == size)


def signature(item):
    return (item.st_dev, item.st_ino, item.st_mode, item.st_uid, item.st_gid, item.st_nlink,
            item.st_size, item.st_mtime_ns, item.st_ctime_ns)


def retain():
    require((os.geteuid(), os.getegid()) == OWNER
            and os.path.realpath("/run/current-system") == PREVIOUS
            and os.path.realpath("/nix/var/nix/profiles/system") == PREVIOUS)
    state = directory(STATE)
    transaction = source = bundle = archive = None
    try:
        transaction = os.open("transaction.lock", os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=state)
        lock_before = os.fstat(transaction)
        regular(lock_before)
        fcntl.flock(transaction, fcntl.LOCK_EX | fcntl.LOCK_NB)
        require(signature(lock_before) == signature(os.stat("transaction.lock", dir_fd=state, follow_symlinks=False)))
        source = directory(SOURCE)
        fcntl.flock(source, fcntl.LOCK_EX | fcntl.LOCK_NB)
        require(set(os.listdir(state)) == {"transaction.lock"})
        try:
            os.stat(ARCHIVE, dir_fd=source, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise Refused("PREVIOUS_INFRASTRUCTURE_RETENTION_REFUSED")
        bundle = os.open(BUNDLE, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=source)
        before = os.fstat(bundle)
        regular(before, BYTES)
        digest = hashlib.sha256()
        remaining = BYTES
        while remaining:
            block = os.read(bundle, min(4 * 1024**2, remaining))
            require(bool(block))
            remaining -= len(block)
            digest.update(block)
        require(not os.read(bundle, 1) and digest.hexdigest() == SHA256)
        require(signature(before) == signature(os.fstat(bundle)) ==
                signature(os.stat(BUNDLE, dir_fd=source, follow_symlinks=False)))
        require(set(os.listdir(state)) == {"transaction.lock"}
                and signature(lock_before) == signature(os.fstat(transaction)))
        os.fsync(bundle)
        # mkdir is exclusive. The new root-private directory is owned solely by
        # this operation under both locks; no existing destination is replaced.
        os.mkdir(ARCHIVE, 0o700, dir_fd=source)
        archive = os.open(ARCHIVE, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=source)
        item = os.fstat(archive)
        require((item.st_uid, item.st_gid) == OWNER and stat.S_IMODE(item.st_mode) == 0o700
                and item.st_dev == before.st_dev and not os.listdir(archive))
        os.fsync(source)
        os.rename(BUNDLE, BUNDLE, src_dir_fd=source, dst_dir_fd=archive)
        os.fsync(archive)
        os.fsync(source)
        after = os.stat(BUNDLE, dir_fd=archive, follow_symlinks=False)
        regular(after, BYTES)
        require((after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) ==
                (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns))
        try:
            os.stat(BUNDLE, dir_fd=source, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise Refused("PREVIOUS_INFRASTRUCTURE_RETENTION_REFUSED")
        require(signature(lock_before) == signature(os.fstat(transaction)) ==
                signature(os.stat("transaction.lock", dir_fd=state, follow_symlinks=False)))
        return {"schema_version": 1, "code": "PREVIOUS_INFRASTRUCTURE_BUNDLE_RETAINED",
                "bytes": BYTES, "sha256": SHA256, "same_inode": True, "same_transaction_lock": True,
                "other_bundles_opened": False, "application_changes": False, "new_bundle_received": False}
    finally:
        for fd in (archive, bundle, source, transaction, state):
            if fd is not None:
                os.close(fd)


def main():
    try:
        require(len(sys.argv) == 1 and os.uname().nodename == "srv1982677")
        os.umask(0o077)
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(Refused("PREVIOUS_INFRASTRUCTURE_RETENTION_REFUSED")))
        signal.alarm(240)
        result = retain()
    except BaseException:
        print('{"schema_version":1,"code":"PREVIOUS_INFRASTRUCTURE_RETENTION_REFUSED"}')
        return 1
    finally:
        signal.alarm(0)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
