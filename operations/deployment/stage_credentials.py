"""Private fixed credential staging; internal call after the paired snapshot."""
import os
from pathlib import Path
import resource
import stat

INPUT = Path("/var/lib/mrjam-identite")
OUTPUT = Path("/run/mrjam-worker-credential-adaptation")
FILES = ("proton-smtp.json", "cycle.json", "fermeture-hook.secret")


class Refused(RuntimeError):
    pass


def directory(path):
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in Path(path).parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def copy_file(source, target, name, owner=0):
    if name not in FILES:
        raise Refused("CREDENTIAL_NAME_REFUSED")
    maximum = 128 if name.endswith(".secret") else 65536
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=source)
    try:
        item = os.fstat(descriptor)
        if (not stat.S_ISREG(item.st_mode) or item.st_uid != owner or item.st_gid != 0
                or item.st_nlink != 1 or stat.S_IMODE(item.st_mode) != 0o600
                or not 0 < item.st_size <= maximum):
            raise Refused("CREDENTIAL_SOURCE_REFUSED")
        raw = os.read(descriptor, maximum + 1)
        after = os.fstat(descriptor)
        if len(raw) != item.st_size or (item.st_size,item.st_mtime_ns,item.st_ctime_ns) != (after.st_size,after.st_mtime_ns,after.st_ctime_ns):
            raise Refused("CREDENTIAL_SOURCE_CHANGED")
    finally:
        os.close(descriptor)
    destination = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400, dir_fd=target)
    try:
        with os.fdopen(destination,"wb",closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fchmod(destination,0o440)
            os.fsync(destination)
    finally:
        os.close(destination)


def prepare():
    if os.geteuid() != 0:
        raise Refused("CREDENTIAL_STAGING_IDENTITY_REFUSED")
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    os.umask(0o077)
    source = directory(INPUT)
    try:
        item=os.fstat(source)
        if item.st_uid != 0 or stat.S_IMODE(item.st_mode) & 0o022:
            raise Refused("CREDENTIAL_DIRECTORY_REFUSED")
        OUTPUT.mkdir(mode=0o700)
        target=directory(OUTPUT)
        try:
            for name in FILES:
                copy_file(source,target,name)
            os.fsync(target)
        finally:
            os.close(target)
    finally:
        os.close(source)


if __name__ == "__main__":
    raise SystemExit(64)
