"""Private paired offline snapshot used by the sealed cutover backend.

No executable CLI, caller-selected source, remote transfer or content output.
Caller must stop every inventoried writer and verify PostgreSQL's final stop.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess

ROOTS = ("postgresql/17", "forgejo", "kanidm", "nextcloud", "redis-nextcloud",
         "mrjam-metier", "mrjam-identite", "acme", "mrjam-vision-admission",
         "mrjam-vision-cycle", "mrjam-vision-archive", "mrjam-worker-credentials")
REQUIRED = frozenset(ROOTS[:8])


class SnapshotRefused(RuntimeError):
    pass


def regular_digest(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    with os.fdopen(descriptor, "rb") as stream:
        metadata = os.fstat(stream.fileno())
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or stat.S_IMODE(metadata.st_mode) != 0o600:
            raise SnapshotRefused("SNAPSHOT_FILE_REFUSED")
        digest = hashlib.sha256()
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


class FrozenSnapshot:
    # Paths are selected by the qualified local backend, never by its CLI.
    def __init__(self, state_root, snapshot_root, tar, owner=0):
        self.state_root, self.root = Path(state_root), Path(snapshot_root)
        self.tar, self.owner = str(tar), owner
        metadata = self.root.lstat()
        if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != owner or stat.S_IMODE(metadata.st_mode) != 0o700:
            raise SnapshotRefused("SNAPSHOT_DIRECTORY_REFUSED")
        self.archive = self.root / "paired-state.tar"
        self.manifest = self.root / "paired-state.json"

    def source(self, relative):
        if relative not in ROOTS:
            raise SnapshotRefused("SNAPSHOT_SOURCE_REFUSED")
        result = self.state_root
        for part in relative.split("/"):
            result = result / part
            try:
                metadata = result.lstat()
            except FileNotFoundError:
                return None
            if not stat.S_ISDIR(metadata.st_mode):
                raise SnapshotRefused("SNAPSHOT_SOURCE_REFUSED")
        return result

    def command(self, args, timeout):
        try:
            result = subprocess.run([self.tar] + args, stdin=subprocess.DEVNULL,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    env={"LANG": "C", "LC_ALL": "C"}, timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired):
            raise SnapshotRefused("SNAPSHOT_OPERATION_FAILED") from None
        if result.returncode != 0:
            raise SnapshotRefused("SNAPSHOT_OPERATION_FAILED")

    def create(self):
        if self.archive.exists() or self.archive.is_symlink() or self.manifest.exists() or self.manifest.is_symlink():
            raise SnapshotRefused("EXISTING_SNAPSHOT_REFUSED")
        present = [name for name in ROOTS if self.source(name) is not None]
        if not REQUIRED.issubset(present):
            raise SnapshotRefused("REQUIRED_SNAPSHOT_SOURCE_MISSING")
        self.verify_storage(present)
        temporary = self.root / "paired-state.partial"
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        os.close(descriptor)
        self.command(["--acls", "--xattrs", "--numeric-owner", "--sparse", "--one-file-system",
                      "-C", str(self.state_root), "-cpf", str(temporary), "--"] + present, 1800)
        descriptor = os.open(temporary, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.rename(temporary, self.archive)
        self.command(["-tf", str(self.archive)], 300)
        value = {"schema_version": 1, "roots": present, "sha256": regular_digest(self.archive)}
        descriptor = os.open(self.manifest, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write((json.dumps(value, sort_keys=True) + "\n").encode())
            stream.flush()
            os.fsync(stream.fileno())
        self.sync_root()

    def verify_storage(self, present):
        # Refuse silent omissions by tar --one-file-system, including bind
        # mounts on the same device. Only technical mount metadata is examined.
        with open("/proc/self/mountinfo", "rb") as stream:
            raw = stream.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise SnapshotRefused("MOUNT_INVENTORY_REFUSED")
        selected = [self.state_root / name for name in present]
        device = self.root.stat().st_dev
        if any(path.stat().st_dev != device for path in selected):
            raise SnapshotRefused("CROSS_FILESYSTEM_RETURN_REFUSED")
        for line in raw.decode("utf-8", "strict").splitlines():
            fields = line.split(" ")
            if len(fields) < 7:
                raise SnapshotRefused("MOUNT_INVENTORY_REFUSED")
            mount = Path(re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), fields[4]))
            if any(mount == path or path in mount.parents for path in selected):
                raise SnapshotRefused("NESTED_STATE_MOUNT_REFUSED")
        tablespaces = self.state_root / "postgresql/17/pg_tblspc"
        if tablespaces.is_symlink() or (tablespaces.exists() and any(tablespaces.iterdir())):
            raise SnapshotRefused("EXTERNAL_TABLESPACE_REFUSED")
        if (self.state_root / "postgresql/17/pg_wal").is_symlink():
            raise SnapshotRefused("EXTERNAL_WAL_REFUSED")

    def sync_root(self):
        descriptor = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def verify(self):
        descriptor = os.open(self.manifest, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor, "rb") as stream:
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or stat.S_IMODE(metadata.st_mode) != 0o600:
                raise SnapshotRefused("SNAPSHOT_MANIFEST_REFUSED")
            data = stream.read(4097)
        if len(data) > 4096:
            raise SnapshotRefused("SNAPSHOT_MANIFEST_REFUSED")
        value = json.loads(data)
        if (set(value) != {"schema_version", "roots", "sha256"} or value["schema_version"] != 1
                or not isinstance(value["roots"], list)
                or value["roots"] != [name for name in ROOTS if name in value["roots"]]
                or not REQUIRED.issubset(value["roots"])
                or value["sha256"] != regular_digest(self.archive)):
            raise SnapshotRefused("SNAPSHOT_INTEGRITY_REFUSED")
        return value

    def restore(self):
        value = self.verify()
        self.verify_storage([name for name in ROOTS if self.source(name) is not None])
        quarantine = self.root / "candidate-state-retained"
        quarantine.mkdir(mode=0o700)
        # Every old and newly introduced root is retained, not deleted. This
        # includes originally absent worker roots, which must not survive return.
        for name in ROOTS:
            source = self.source(name)
            if source is not None:
                destination = quarantine / name
                destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                os.rename(source, destination)
        self.command(["--acls", "--xattrs", "--numeric-owner", "-C", str(self.state_root),
                      "-xpf", str(self.archive)], 1800)
        if any(self.source(name) is None for name in value["roots"]):
            raise SnapshotRefused("SNAPSHOT_RETURN_INCOMPLETE")
        # A tar exit status is not a durability barrier. Flush restored files
        # and directories before the backend may restart PostgreSQL or reopen.
        for name in value["roots"]:
            for directory, folders, files in os.walk(self.state_root / name, followlinks=False, topdown=False):
                for child in files:
                    path = Path(directory) / child
                    if path.is_symlink():
                        continue
                    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                    try:
                        if stat.S_ISREG(os.fstat(descriptor).st_mode):
                            os.fsync(descriptor)
                    finally:
                        os.close(descriptor)
                descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
        descriptor = os.open(self.state_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        self.sync_root()


if __name__ == "__main__":
    raise SystemExit(64)
