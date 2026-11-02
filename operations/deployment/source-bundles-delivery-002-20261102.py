"""Receive exactly nine sealed source bundles, without importing or executing them.

The input is the concatenation of the nine bundle byte strings in NAMES order.
It contains no file names, paths, metadata, commands or configurable options.
Only RELEASE is replaced in a separately reviewed operational copy.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import secrets
import signal
import stat
import sys

RELEASE = {'schema_version': 1, 'stream_bytes': 4050642782, 'stream_sha256': '6b48b4af02ddf7510723cefddcb082fdde1ec4a45932eae6ee5a4b069b763865', 'required_free_bytes': 5124384606, 'bundles': [{'name': 'Signature', 'bytes': 417325, 'sha256': '241b188f6f7c8ec73fae1b21ed77ed0cd795129a7d29d4d06bb20334171adfa6'}, {'name': 'apprendre-a-demontrer', 'bytes': 313556, 'sha256': 'a173ffcb239eecff6c1dbb576aecc4839520468f499d88f49077a875f505c3a5'}, {'name': 'etp-vie-affective', 'bytes': 77190157, 'sha256': 'fbc31c486d65dfe7e65144a6a0eec3453cc21c2e84454dc2111a1559e5a6c127'}, {'name': 'matheval', 'bytes': 1154607, 'sha256': '7107a68476e0b01ac640c938fecf4a5c0574598cfc593c218ebb41a4d52d7a76'}, {'name': 'mrjam-plateforme', 'bytes': 412039, 'sha256': '33669679f76ef1131cc3597996ef339eae9bf4f34e17939d99be5c994c13b15a'}, {'name': 'mrjam-validation', 'bytes': 2716212, 'sha256': '9713e3481bfc2a44b9f4abf86e0a54214b0bccb7ea0be409c99c64517471953b'}, {'name': 'style-mrjam', 'bytes': 4449846, 'sha256': '1ddb5054c7bf5d43c27ddf276304b8c52d6dbe5860d3eb159ba98c59e9880b84'}, {'name': 'vision', 'bytes': 9577065, 'sha256': '25da54614a63892ff737f8c8f928d707ffdeb9ba88aab8dc8223c3a9ea7da47d'}, {'name': 'vps-infrastructure', 'bytes': 3954411975, 'sha256': 'a1696d45de918ad637d1dd792bb700f0fb7af3f0567ed39904bdd9b0251efd4f'}]}
PREVIOUS = "/nix/store/jn9rf2fgk2y6dbhdnjwkmfww3pchkyb9-nixos-system-nixos-26.05.8639.c5c4a43b0e80"
DIRECTORY = Path("/var/lib/mrjam-source-import")
OWNER = (0, 0)
NAMES = ("Signature", "apprendre-a-demontrer", "etp-vie-affective", "matheval",
         "mrjam-plateforme", "mrjam-validation", "style-mrjam", "vision", "vps-infrastructure")
GIB = 1024 ** 3
BLOCK = 1024 ** 2


class Refused(RuntimeError):
    pass


def require(value):
    if not value:
        raise Refused("SOURCE_BUNDLES_REFUSED")


def validate_release(value):
    require(type(value) is dict and set(value) == {
        "schema_version", "stream_bytes", "stream_sha256", "required_free_bytes", "bundles"})
    require(type(value["schema_version"]) is int and value["schema_version"] == 1)
    require(type(value["stream_sha256"]) is str
            and re.fullmatch(r"[a-f0-9]{64}", value["stream_sha256"]))
    require(type(value["bundles"]) is list and len(value["bundles"]) == len(NAMES))
    total = 0
    for name, item in zip(NAMES, value["bundles"]):
        require(type(item) is dict and set(item) == {"name", "bytes", "sha256"})
        require(type(item["name"]) is str and item["name"] == name)
        require(type(item["bytes"]) is int and 0 < item["bytes"] <= 64 * GIB)
        require(type(item["sha256"]) is str and re.fullmatch(r"[a-f0-9]{64}", item["sha256"]))
        total += item["bytes"]
    require(type(value["stream_bytes"]) is int and value["stream_bytes"] == total <= 64 * GIB)
    require(type(value["required_free_bytes"]) is int
            and total + GIB <= value["required_free_bytes"] <= 65 * GIB)
    return value


def protected_directory(path):
    """Walk fixed ancestors by descriptor, never following a symbolic link."""
    require(path.is_absolute() and ".." not in path.parts)
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        for index, part in enumerate(path.parts[1:], 1):
            if index == len(path.parts) - 1:
                try:
                    os.mkdir(part, 0o700, dir_fd=descriptor)
                    os.fsync(descriptor)
                except FileExistsError:
                    pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                            dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
            item = os.fstat(descriptor)
            require(item.st_uid in (0, OWNER[0]) and not stat.S_IMODE(item.st_mode) & 0o022)
        item = os.fstat(descriptor)
        require((item.st_uid, item.st_gid) == OWNER and stat.S_IMODE(item.st_mode) == 0o700)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def fingerprint(item):
    return (item.st_dev, item.st_ino, item.st_mode, item.st_uid, item.st_gid, item.st_nlink,
            item.st_size, item.st_mtime_ns, item.st_ctime_ns)


def verify_file(directory, name, expected, *, missing_allowed=False):
    try:
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                             dir_fd=directory)
    except FileNotFoundError:
        require(missing_allowed)
        return None
    try:
        before = os.fstat(descriptor)
        require(stat.S_ISREG(before.st_mode) and (before.st_uid, before.st_gid) == OWNER
                and stat.S_IMODE(before.st_mode) == 0o600 and before.st_nlink == 1
                and before.st_size == expected["bytes"])
        digest = hashlib.sha256()
        remaining = expected["bytes"]
        while remaining:
            block = os.read(descriptor, min(BLOCK, remaining))
            require(bool(block))
            remaining -= len(block)
            digest.update(block)
        require(not os.read(descriptor, 1) and digest.hexdigest() == expected["sha256"])
        after = os.fstat(descriptor)
        current = os.stat(name, dir_fd=directory, follow_symlinks=False)
        require(fingerprint(before) == fingerprint(after) == fingerprint(current))
        return fingerprint(after)
    finally:
        os.close(descriptor)


def write_all(descriptor, block):
    view = memoryview(block)
    while view:
        count = os.write(descriptor, view)
        require(count > 0)
        view = view[count:]


def receive(stream, directory, release):
    """Caller holds the directory lock; accept all bytes before creating finals."""
    prior = {item["name"]: verify_file(directory, item["name"] + ".bundle", item,
                                     missing_allowed=True) for item in release["bundles"]}
    staging_name = ".incoming-" + secrets.token_hex(16)
    os.mkdir(staging_name, 0o700, dir_fd=directory)
    staging = None
    created = []
    try:
        staging = os.open(staging_name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                          dir_fd=directory)
        meta = os.fstat(staging)
        require((meta.st_uid, meta.st_gid) == OWNER and stat.S_IMODE(meta.st_mode) == 0o700)
        complete = hashlib.sha256()
        for item in release["bundles"]:
            name = item["name"] + ".bundle"
            descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                                 0o600, dir_fd=staging)
            created.append(name)
            try:
                remaining = item["bytes"]
                digest = hashlib.sha256()
                while remaining:
                    requested = min(BLOCK, remaining)
                    block = stream.read(requested)
                    require(type(block) is bytes and 0 < len(block) <= requested)
                    remaining -= len(block)
                    digest.update(block)
                    complete.update(block)
                    write_all(descriptor, block)
                require(digest.hexdigest() == item["sha256"])
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        require(stream.read(1) == b"" and complete.hexdigest() == release["stream_sha256"])
        os.fsync(staging)
        # Re-read every staged file and check every destination before any final
        # installation; a late mismatch cannot accept an earlier valid segment.
        for item in release["bundles"]:
            name = item["name"] + ".bundle"
            verify_file(staging, name, item)
            require(verify_file(directory, name, item, missing_allowed=True) == prior[item["name"]])
        installed = 0
        for item in release["bundles"]:
            name = item["name"] + ".bundle"
            if prior[item["name"]] is None:
                # link() cannot replace an unexpected destination. Removing the
                # staging name immediately restores the final inode's nlink=1.
                os.link(name, name, src_dir_fd=staging, dst_dir_fd=directory, follow_symlinks=False)
                installed += 1
            os.unlink(name, dir_fd=staging)
            created.remove(name)
        os.fsync(directory)
        for item in release["bundles"]:
            verify_file(directory, item["name"] + ".bundle", item)
        return installed
    finally:
        if staging is not None:
            try:
                for name in created:
                    os.unlink(name, dir_fd=staging)
            finally:
                os.close(staging)
        os.rmdir(staging_name, dir_fd=directory)
        os.fsync(directory)


def deliver(release, stream):
    release = validate_release(release)
    require((os.geteuid(), os.getegid()) == OWNER
            and os.path.realpath("/run/current-system") == PREVIOUS)
    directory = protected_directory(DIRECTORY)
    try:
        fcntl.flock(directory, fcntl.LOCK_EX | fcntl.LOCK_NB)
        filesystem = os.fstatvfs(directory)
        require(filesystem.f_bavail * filesystem.f_frsize >= release["required_free_bytes"])
        installed = receive(stream, directory, release)
    finally:
        os.close(directory)
    return {"schema_version": 1, "code": "SOURCE_BUNDLES_RECEIVED", "bundle_count": len(NAMES),
            "created_count": installed, "already_present_count": len(NAMES) - installed,
            "stream_sha256": release["stream_sha256"], "forgejo_imported": False,
            "application_activation": False}


def interrupted(_signum, _frame):
    raise Refused("SOURCE_BUNDLES_REFUSED")


def main():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    os.umask(0o077)
    signal.signal(signal.SIGALRM, interrupted)
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    signal.alarm(900)
    try:
        require(len(sys.argv) == 1)
        result = deliver(RELEASE, sys.stdin.buffer)
    except Exception:
        result = {"schema_version": 1, "code": "SOURCE_BUNDLES_REFUSED"}
        status = 1
    else:
        status = 0
    finally:
        signal.alarm(0)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return status


if __name__ == "__main__":
    sys.exit(main())
