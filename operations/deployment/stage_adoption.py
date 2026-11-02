"""Prepare closed, private SQLite images for the three explicit adopters.

Called only inside the sealed cutover after all writers have stopped. Source
contents stay on the VPS. There is no CLI, caller-selected SQL or path output.
SQLite's backup API includes committed WAL state; copying a live main file does
not. The service sandbox subsequently mounts each staging directory read-only.
"""
import os
from pathlib import Path
import sqlite3
import stat
import time

PROFILES = {
    "mrjam-admission-adoption": (947, 947, (
        ("admission/admissions.sqlite", "requests.sqlite"),
        ("admission/courriels.sqlite", "mail.sqlite"))),
    "mrjam-cycle-mail-adoption": (945, 945, (("cycle/courriels.sqlite", "mail.sqlite"),)),
    "mrjam-archive-mail-adoption": (943, 943, (
        ("fermeture/courriels.sqlite", "closure.sqlite"),
        ("courriel/file.sqlite", "global.sqlite"))),
}
MAXIMUM = 64 * 1024 * 1024


class Refused(RuntimeError):
    pass


def sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def image(source, destination, source_uid=984, source_gid=984, target_gid=0, owner=0):
    """Internal implementation; production callers supply only fixed profiles."""
    source, destination = Path(source), Path(destination)
    for parent in reversed(source.parents):
        if not stat.S_ISDIR(parent.lstat().st_mode):
            raise Refused("SOURCE_DIRECTORY_REFUSED")
    metadata = source.lstat()
    if (not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1
            or metadata.st_uid != source_uid or metadata.st_gid != source_gid
            or stat.S_IMODE(metadata.st_mode) != 0o600 or not 0 < metadata.st_size <= MAXIMUM):
        raise Refused("SOURCE_IMAGE_REFUSED")
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    os.close(descriptor)
    deadline = time.monotonic() + 30
    reader = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=1)
    writer = sqlite3.connect(destination)
    try:
        reader.execute("PRAGMA query_only=ON")
        reader.execute("PRAGMA trusted_schema=OFF")
        reader.execute("BEGIN")
        pages = reader.execute("PRAGMA page_count").fetchone()[0]
        page_size = reader.execute("PRAGMA page_size").fetchone()[0]
        if type(pages) is not int or type(page_size) is not int or pages * page_size > MAXIMUM:
            raise Refused("SOURCE_LIMIT_REFUSED")
        def progress(status, remaining, total):
            if status not in (sqlite3.SQLITE_OK, sqlite3.SQLITE_DONE) or time.monotonic() > deadline:
                raise Refused("IMAGE_OPERATION_REFUSED")
            if remaining < 0 or total * page_size > MAXIMUM:
                raise Refused("SOURCE_LIMIT_REFUSED")
        reader.backup(writer, pages=256, progress=progress, sleep=0)
        writer.execute("PRAGMA journal_mode=DELETE")
        if writer.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
            raise Refused("IMAGE_INTEGRITY_REFUSED")
    except Exception:
        # Retain partial files privately for explicit recovery, never overwrite.
        raise Refused("IMAGE_OPERATION_REFUSED") from None
    finally:
        writer.close()
        reader.close()
    descriptor = os.open(destination, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        if os.fstat(descriptor).st_size > MAXIMUM:
            raise Refused("IMAGE_LIMIT_REFUSED")
        os.fchown(descriptor, owner, target_gid)
        os.fchmod(descriptor, 0o440)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def prepare():
    if os.geteuid() != 0:
        raise Refused("STAGING_IDENTITY_REFUSED")
    os.umask(0o077)
    for name, (uid, gid, entries) in PROFILES.items():
        directory = Path("/run") / name
        directory.mkdir(mode=0o700)  # Existing/partial publication is not replayed.
        for relative, target in entries:
            image(Path("/var/lib/mrjam-metier") / relative, directory / target, target_gid=gid)
        sync_directory(directory)
        os.chown(directory, uid, gid)
    sync_directory("/run")


if __name__ == "__main__":
    raise SystemExit(64)
