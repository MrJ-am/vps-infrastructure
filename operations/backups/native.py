"""Closed native component backups; never a cutover rollback or a remote export.

Each PostgreSQL dump, SQLite backup and Kanidm export is internally consistent.
They are separate online snapshots, not one atomic cross-service snapshot.
The offline paired snapshot remains the only pre-opening cutover return point.
"""
from datetime import datetime, timedelta, timezone
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time

DATABASES = ("vision", "vision_journal", "matheval")
SQLITES = {
    "sessions.sqlite": ("mrjam-metier/log/sessions.sqlite", 984, 984),
    "admissions.sqlite": ("mrjam-vision-admission/admissions.sqlite", 947, 947),
    "cycle.sqlite": ("mrjam-vision-cycle/courriels.sqlite", 945, 945),
    "archive.sqlite": ("mrjam-vision-archive/courriels.sqlite", 943, 943),
}
FILES = tuple(name + ".dump" for name in DATABASES) + tuple(SQLITES) + ("kanidm.json.gz",)
STAMP = re.compile(r"[0-9]{8}T[0-9]{6}Z-[0-9a-f]{16}")
MAXIMUM_SQLITE = 1024 * 1024 * 1024


class Refused(RuntimeError):
    pass


def sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def open_regular(path, owner=None, maximum=None):
    path = Path(path)
    if not path.is_absolute():
        raise Refused("BACKUP_REFERENCE_REFUSED")
    current = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parts[1:-1]:
            next_directory = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current)
            os.close(current)
            current = next_directory
        descriptor = os.open(path.name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=current)
    finally:
        os.close(current)
    metadata = os.fstat(descriptor)
    if (not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1
            or (owner is not None and metadata.st_uid != owner)
            or (maximum is not None and metadata.st_size > maximum)):
        os.close(descriptor)
        raise Refused("BACKUP_REFERENCE_REFUSED")
    return descriptor, metadata


def digest(path):
    descriptor, _ = open_regular(path)
    value = hashlib.sha256()
    with os.fdopen(descriptor, "rb") as stream:
        while block := stream.read(1024 * 1024):
            value.update(block)
    return value.hexdigest()


def sqlite_image(source, destination, uid, gid):
    source, destination = Path(source), Path(destination)
    descriptor, before = open_regular(source, uid, MAXIMUM_SQLITE)
    os.close(descriptor)
    if before.st_gid != gid or stat.S_IMODE(before.st_mode) != 0o600 or before.st_size == 0:
        raise Refused("BACKUP_SQLITE_REFUSED")
    destination.touch(mode=0o600, exist_ok=False)
    deadline = time.monotonic() + 60
    reader = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=1)
    writer = sqlite3.connect(destination)
    try:
        reader.execute("PRAGMA query_only=ON")
        reader.execute("PRAGMA trusted_schema=OFF")
        reader.execute("BEGIN")
        page_size = reader.execute("PRAGMA page_size").fetchone()[0]

        def progress(status, remaining, total):
            if (status not in (sqlite3.SQLITE_OK, sqlite3.SQLITE_DONE) or time.monotonic() > deadline
                    or remaining < 0 or total < 0 or total * page_size > MAXIMUM_SQLITE):
                raise Refused("BACKUP_SQLITE_LIMIT_REFUSED")

        reader.backup(writer, pages=256, progress=progress, sleep=0)
        writer.execute("PRAGMA journal_mode=DELETE")
        if writer.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
            raise Refused("BACKUP_SQLITE_INTEGRITY_REFUSED")
    finally:
        writer.close()
        reader.close()
    descriptor, after = open_regular(source, uid, MAXIMUM_SQLITE)
    os.close(descriptor)
    if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
        raise Refused("BACKUP_SQLITE_REPLACED")


def recipient(path):
    descriptor, _ = open_regular(path, 0, 8192)
    with os.fdopen(descriptor, "rb") as stream:
        value = json.loads(stream.read(8193))
    result = value.get("age_recipient") if isinstance(value, dict) else None
    if not isinstance(result, str) or not re.fullmatch(r"age1[a-z0-9]{58}", result):
        raise Refused("BACKUP_RECIPIENT_REFUSED")
    return result


class NativeBackup:
    # Dependency injection is for local invented fixtures only. The entrypoint
    # below supplies fixed paths, identities and commands, and accepts no args.
    def __init__(self, tools, state, root, kanidm, identity=None, owner=0, runner=None):
        self.tools = tools
        self.state, self.root, self.kanidm = Path(state), Path(root), Path(kanidm)
        self.owner = owner
        self.identity = SQLITES if identity is None else identity
        self.runner = runner
        metadata = self.root.lstat()
        if (not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != owner
                or stat.S_IMODE(metadata.st_mode) != 0o700):
            raise Refused("BACKUP_DIRECTORY_REFUSED")

    def run(self, arguments, output=None, input_file=None):
        if self.runner is not None:
            return self.runner(arguments, output, input_file)
        try:
            result = subprocess.run(arguments, stdin=input_file or subprocess.DEVNULL,
                                    stdout=output or subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    env={"LANG": "C", "LC_ALL": "C"}, timeout=900, check=False)
        except (OSError, subprocess.TimeoutExpired):
            raise Refused("BACKUP_COMMAND_REFUSED") from None
        if result.returncode != 0:
            raise Refused("BACKUP_COMMAND_REFUSED")

    def capture(self, directory):
        self.run([self.tools["systemctl"], "start", "mrjam-kanidm-backup.service"])
        for name in DATABASES:
            path = directory / (name + ".dump")
            with path.open("xb") as output:
                os.chmod(path, 0o600)
                self.run([self.tools["runuser"], "-u", "postgres", "--", self.tools["pg_dump"],
                          "--host=/run/postgresql", "--format=custom", name], output=output)
            self.run([self.tools["pg_restore"], "--list", str(path)])
        for name, (relative, uid, gid) in self.identity.items():
            sqlite_image(self.state / relative, directory / name, uid, gid)
        descriptor, metadata = open_regular(self.kanidm, self.owner if self.owner != 0 else 983)
        if stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_size == 0:
            os.close(descriptor)
            raise Refused("BACKUP_KANIDM_REFUSED")
        path = directory / "kanidm.json.gz"
        with os.fdopen(descriptor, "rb") as source, path.open("xb") as target:
            os.chmod(path, 0o600)
            shutil.copyfileobj(source, target, 1024 * 1024)
        # A zero exit from the upstream CLI does not prove it emitted a backup.
        # Read the gzip stream to its trailer without printing or parsing data.
        with gzip.open(path, "rb") as stream:
            size = 0
            while block := stream.read(1024 * 1024):
                size += len(block)
                if size > 8 * 1024 * 1024 * 1024:
                    raise Refused("BACKUP_KANIDM_LIMIT_REFUSED")
            if size == 0:
                raise Refused("BACKUP_KANIDM_EMPTY")
        if set(path.name for path in directory.iterdir()) != set(FILES):
            raise Refused("BACKUP_COMPONENT_SET_REFUSED")

    def publish(self, age_recipient):
        if not re.fullmatch(r"age1[a-z0-9]{58}", age_recipient):
            raise Refused("BACKUP_RECIPIENT_REFUSED")
        lock = os.open(self.root / ".native-backup.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            metadata = os.fstat(lock)
            if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != self.owner
                    or metadata.st_nlink != 1 or stat.S_IMODE(metadata.st_mode) != 0o600):
                raise Refused("BACKUP_LOCK_REFUSED")
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return self._publish(age_recipient)
        finally:
            os.close(lock)

    def _publish(self, age_recipient):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + os.urandom(8).hex()
        work = Path(tempfile.mkdtemp(prefix=".native-pending-", dir=self.root))
        source = work / "components"
        source.mkdir(mode=0o700)
        self.capture(source)
        bundle = work / "components.tar"
        self.run([self.tools["tar"], "-C", str(source), "-cpf", str(bundle), "--", *FILES])
        bundle.chmod(0o600)
        ephemeral_key = work / "ephemeral-key"
        self.run([self.tools["age_keygen"], "-o", str(ephemeral_key)])
        ephemeral_key.chmod(0o600)
        ephemeral_public = work / "ephemeral-public"
        with ephemeral_public.open("xb") as output:
            self.run([self.tools["age_keygen"], "-y", str(ephemeral_key)], output=output)
        public = ephemeral_public.read_text().strip()
        if not re.fullmatch(r"age1[a-z0-9]{58}", public):
            raise Refused("BACKUP_ENVELOPE_REFUSED")
        publication = work / "publication"
        publication.mkdir(mode=0o700)
        encrypted = publication / "components.tar.age"
        key = publication / "key.age"
        self.run([self.tools["age"], "-r", public, "-o", str(encrypted), str(bundle)])
        self.run([self.tools["age"], "-r", age_recipient, "-o", str(key), str(ephemeral_key)])
        # As in the historical Forgejo envelope, verify the actual ciphertext
        # with its disposable key before discarding that key or publishing.
        verified = work / "verified.tar"
        self.run([self.tools["age"], "-d", "-i", str(ephemeral_key), "-o", str(verified), str(encrypted)])
        if digest(bundle) != digest(verified):
            raise Refused("BACKUP_ENCRYPTION_VERIFICATION_REFUSED")
        for path in (encrypted, key):
            path.chmod(0o600)
        document = {"schema_version": 1, "kind": "native-component-backup", "created": stamp,
                    "components": list(FILES), "cross_component_atomic": False,
                    "requires_current_erasure_journal": True,
                    "files": {"components.tar.age": digest(encrypted), "key.age": digest(key)}}
        manifest = publication / "manifest.json"
        manifest.write_text(json.dumps(document, sort_keys=True) + "\n")
        manifest.chmod(0o600)
        for path in publication.iterdir():
            descriptor, _ = open_regular(path, self.owner)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        sync_directory(publication)
        target = self.root / stamp
        if target.exists() or target.is_symlink():
            raise Refused("BACKUP_PUBLICATION_EXISTS")
        os.rename(publication, target)
        sync_directory(self.root)
        shutil.rmtree(work)
        sync_directory(self.root)
        self.prune(datetime.now(timezone.utc) - timedelta(days=30))
        return target

    def prune(self, before):
        # Only this new, closed format is eligible for its source-declared
        # 30-day retention. Historical files and incomplete work stay untouched.
        for directory in self.root.iterdir():
            if not STAMP.fullmatch(directory.name) or directory.is_symlink() or not directory.is_dir():
                continue
            try:
                date = datetime.strptime(directory.name[:16], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if date >= before:
                continue
            if {path.name for path in directory.iterdir()} != {"manifest.json", "components.tar.age", "key.age"}:
                continue
            try:
                descriptor, metadata = open_regular(directory / "manifest.json", self.owner, 8192)
                with os.fdopen(descriptor, "rb") as stream:
                    document = json.loads(stream.read(8193))
                if (not isinstance(document, dict)
                        or set(document) != {"schema_version", "kind", "created", "components", "cross_component_atomic",
                                             "requires_current_erasure_journal", "files"}
                        or document.get("schema_version") != 1 or document.get("kind") != "native-component-backup"
                        or document.get("created") != directory.name or document.get("components") != list(FILES)
                        or document.get("cross_component_atomic") is not False
                        or document.get("requires_current_erasure_journal") is not True
                        or set(document.get("files", {})) != {"components.tar.age", "key.age"}):
                    continue
                if any(digest(directory / name) != value for name, value in document["files"].items()):
                    continue
            except (OSError, ValueError, Refused):
                continue
            shutil.rmtree(directory)
        sync_directory(self.root)


def main():
    if len(sys.argv) != 1 or os.geteuid() != 0:
        raise Refused("BACKUP_IDENTITY_REFUSED")
    os.umask(0o077)
    tools = json.loads('@commands_json@')
    backup = NativeBackup(tools, "/var/lib", "/var/backup/mrjam/native-v1",
                          "/run/mrjam-kanidm-backup/kanidm.json.gz")
    backup.publish(recipient("/run/credentials/mrjam-sauvegarde.service/archive-configuration"))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print('{"error":"NATIVE_BACKUP_REFUSED"}', file=sys.stderr)
        raise SystemExit(1)
    print('{"status":"ok"}')
