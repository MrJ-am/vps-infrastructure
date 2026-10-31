#!/usr/bin/env python3
"""Publish only configured public source bundles, under the worker's lock.

No request protocol, fetch, candidate command or deployment authority. The
unchanged worker independently checks every published byte again at execution.
"""
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys

_spec = importlib.util.spec_from_file_location("mrjam_worker", Path(__file__).with_name("worker.py"))
worker = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(worker)
require = worker.require
Refused = worker.Refused

CATALOG = Path("/etc/mrjam-validation-staging/catalog.json")
INPUT = Path("/var/lib/mrjam-validation-input")
LOCK = Path("/run/mrjam-validation-worker/operation.lock")
STORE = Path("/nix/store")
MAX_FILES = 4096
MAX_BYTES = 32 * 1024 * 1024
MAX_MANIFEST = 4 * 1024 * 1024
MAX_RETAINED = 2
MAX_NODES = 16384


def catalog(value):
    worker.exact(value, ("schema_version", "rules_revision", "proposals"))
    require(type(value["schema_version"]) is int and value["schema_version"] == 1, "INVALID_VERSION")
    rules = value["rules_revision"]
    require(type(rules) is str and re.fullmatch("[0-9a-f]{40}", rules), "INVALID_RULES")
    entries = value["proposals"]
    require(type(entries) is list and 1 <= len(entries) <= MAX_RETAINED, "RETENTION_LIMIT")
    seen = set()
    for entry in entries:
        worker.exact(entry, ("sha256", "source_store"))
        proposal, source = entry["sha256"], entry["source_store"]
        require(type(proposal) is str and worker.HEX.fullmatch(proposal), "INVALID_PROPOSAL")
        require(proposal not in seen, "DUPLICATE_PROPOSAL")
        seen.add(proposal)
        require(type(source) is str and worker.STORE.fullmatch(source), "INVALID_STORE_PATH")
    return value


def source_bytes(path, limit, owner):
    """Store optimisation may hardlink files; staged copies must have one link."""
    info = os.lstat(path)
    require(stat.S_ISREG(info.st_mode) and info.st_uid == owner and
            not info.st_mode & 0o222 and info.st_size <= limit, "UNTRUSTED_SOURCE")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        signature = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        require(signature(before) == signature(info), "SOURCE_CHANGED")
        raw = stream.read(limit + 1)
        require(len(raw) == before.st_size and signature(os.fstat(stream.fileno())) == signature(before), "SOURCE_CHANGED")
    return raw


def manifest(raw, proposal, rules):
    require(len(raw) <= MAX_MANIFEST and hashlib.sha256(raw).hexdigest() == proposal, "MANIFEST_MISMATCH")
    value = worker.parse(raw)
    worker.exact(value, ("schema_version", "rules_revision", "files"))
    require(type(value["schema_version"]) is int and value["schema_version"] == 1, "INVALID_VERSION")
    require(value["rules_revision"] == rules, "RULES_MISMATCH")
    files = value["files"]
    require(type(files) is list and 0 < len(files) <= MAX_FILES, "FILE_LIMIT")
    names, directories, total = {"manifest.json"}, set(), 0
    for entry in files:
        worker.exact(entry, ("path", "bytes", "sha256"))
        name = entry["path"]
        require(type(name) is str and re.fullmatch(r"[A-Za-z0-9._+~/-]{1,300}", name) and
                not name.startswith("/") and str(PurePosixPath(name)) == name and
                all(p not in (".", "..") for p in PurePosixPath(name).parts), "INVALID_PATH")
        require(name not in names, "DUPLICATE_PATH")
        names.add(name)
        require(type(entry["bytes"]) is int and 0 <= entry["bytes"] <= MAX_BYTES and
                type(entry["sha256"]) is str and worker.HEX.fullmatch(entry["sha256"]), "INVALID_FILE")
        total += entry["bytes"]
        require(total <= MAX_BYTES, "INPUT_LIMIT")
        directories.update(str(p) for p in PurePosixPath(name).parents if str(p) != ".")
    require(not names.intersection(directories), "PATH_COLLISION")
    require(len(names) + len(directories) <= MAX_NODES, "FILE_LIMIT")
    return value, names, directories


def source_tree(root, names, directories, owner):
    worker.root_readonly(root, directory=True, owner=owner)
    seen, count = set(), 0
    for base, subdirs, files in os.walk(root, followlinks=False):
        count += len(subdirs) + len(files)
        require(count <= MAX_NODES, "FILE_LIMIT")
        for name in subdirs:
            path = Path(base)/name
            require(str(path.relative_to(root)) in directories, "UNDECLARED_SOURCE")
            worker.root_readonly(path, directory=True, owner=owner)
        for name in files:
            path = Path(base)/name
            relative = str(path.relative_to(root))
            require(relative in names, "UNDECLARED_SOURCE")
            info = os.lstat(path)
            require(stat.S_ISREG(info.st_mode) and info.st_uid == owner and
                    not info.st_mode & 0o222, "UNTRUSTED_SOURCE")
            seen.add(relative)
    require(seen == names, "SOURCE_INCOMPLETE")


def checked_published(root, proposal, owner):
    info = os.lstat(root/proposal)
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == owner and
            stat.S_IMODE(info.st_mode) in (0o555, 0o755), "UNTRUSTED_INPUT")
    # Moving a directory across parents requires owner-write on Linux. If the
    # writer died after rename, restore the sealed mode and recheck every byte.
    (root/proposal).chmod(0o555)
    raw = worker.checked_bytes(root/proposal/"manifest.json", MAX_MANIFEST, owner=owner)
    rules = worker.parse(raw).get("rules_revision")
    require(type(rules) is str and re.fullmatch("[0-9a-f]{40}", rules), "INVALID_RULES")
    manifest(raw, proposal, rules)
    root.chmod(0o555)
    try:
        worker.verify_input(root, proposal, rules, owner=owner)
    finally:
        root.chmod(0o755)


def erase_private_stage(stage, owner):
    """Recover only this fixed, owner-only staging directory, without following links."""
    info = os.lstat(stage)
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == owner and
            stat.S_IMODE(info.st_mode) == 0o700, "UNSAFE_STAGE")
    count, total = 0, 0
    for base, subdirs, files in os.walk(stage, followlinks=False):
        count += len(subdirs) + len(files)
        require(count <= MAX_RETAINED * (MAX_NODES + 2), "STAGE_LIMIT")
        for name in subdirs + files:
            path = Path(base)/name
            info = os.lstat(path)
            require(info.st_uid == owner and not info.st_mode & 0o022, "UNSAFE_STAGE")
            require(stat.S_ISDIR(info.st_mode) or (stat.S_ISREG(info.st_mode) and info.st_nlink == 1), "UNSAFE_STAGE")
            if stat.S_ISREG(info.st_mode):
                total += info.st_size
                require(info.st_size <= MAX_BYTES and total <= MAX_RETAINED * (MAX_BYTES + MAX_MANIFEST), "STAGE_LIMIT")
    # All descendants are owned by this component and inaccessible to candidates.
    # Python's fd-based rmtree also refuses directory-symlink substitutions.
    require(shutil.rmtree.avoids_symlink_attacks, "SAFE_REMOVAL_UNAVAILABLE")
    for base, _, _ in os.walk(stage, topdown=False):
        Path(base).chmod(0o700)
    shutil.rmtree(stage)


def fsync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_copy(path, raw):
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    with path.open("xb") as out:
        out.write(raw)
        out.flush()
        os.fchmod(out.fileno(), 0o444)
        os.fsync(out.fileno())


def reconcile(configuration, root=INPUT, lock_path=LOCK, *, owner=0, store=STORE):
    """Paths/owner are internal test seams; the installed CLI exposes none of them."""
    configuration = catalog(configuration)
    info = os.lstat(root)
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == owner and
            stat.S_IMODE(info.st_mode) in (0o555, 0o755), "UNSAFE_INPUT_ROOT")
    fd = os.open(lock_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as lock:
        info = os.fstat(lock.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_uid == owner and info.st_nlink == 1 and
                stat.S_IMODE(info.st_mode) == 0o440, "UNSAFE_LOCK")
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Refused("BUSY") from None
        root.chmod(0o755)
        try:
            return publish_locked(configuration, root, owner, store)
        finally:
            # A killed writer leaves 0755, which the unchanged worker rejects.
            # The next invocation accepts only this owner-only recovery mode.
            root.chmod(0o555)
            fsync_dir(root)


def publish_locked(configuration, root, owner, store):
    stage = root/".staging"
    recovered = stage.exists() or stage.is_symlink()
    if recovered:
        erase_private_stage(stage, owner)
    existing = set()
    with os.scandir(root) as entries:
        for entry in entries:
            require(worker.HEX.fullmatch(entry.name), "UNKNOWN_PUBLISHED_ENTRY")
            existing.add(entry.name)
            # A crash after rename may leave both old and new catalogues.
            require(len(existing) <= MAX_RETAINED * 2, "RETENTION_LIMIT")
            checked_published(root, entry.name, owner)
    desired = {entry["sha256"] for entry in configuration["proposals"]}
    # Validate every selected bundle even when an identical publication exists.
    prepared = []
    for entry in configuration["proposals"]:
        source = store/Path(entry["source_store"]).name
        worker.root_readonly(source, directory=True, owner=owner)
        raw = source_bytes(source/"manifest.json", MAX_MANIFEST, owner)
        value, names, directories = manifest(raw, entry["sha256"], configuration["rules_revision"])
        source_tree(source, names, directories, owner)
        prepared.append((entry["sha256"], source, raw, value))
    published = []
    try:
        stage.mkdir(mode=0o700)
        # One view per proposal permits the unchanged worker to verify it.
        for proposal, source, raw, value in prepared:
            view = stage/proposal
            view.mkdir(mode=0o700)
            target = view/proposal
            target.mkdir(mode=0o700)
            for entry in value["files"]:
                content = source_bytes(source/entry["path"], entry["bytes"], owner)
                require(len(content) == entry["bytes"] and hashlib.sha256(content).hexdigest() == entry["sha256"], "FILE_HASH_MISMATCH")
                write_copy(target/entry["path"], content)
            write_copy(target/"manifest.json", raw)
            for base, _, _ in os.walk(target, topdown=False):
                Path(base).chmod(0o555)
                fsync_dir(base)
            view.chmod(0o500)
            worker.verify_input(view, proposal, configuration["rules_revision"], owner=owner)
            fsync_dir(view)
        fsync_dir(stage)
        # No publication or retirement happens until ALL copies are valid.
        for proposal, _, _, _ in prepared:
            if proposal not in existing:
                (stage/proposal).chmod(0o700)
                (stage/proposal/proposal).chmod(0o755)
                os.rename(stage/proposal/proposal, root/proposal)
                (root/proposal).chmod(0o555)
                fsync_dir(root)
                published.append(proposal)
        # Drop unused copies before retiring old entries, keeping cleanup bounded.
        erase_private_stage(stage, owner)
        stage.mkdir(mode=0o700)
        for proposal in sorted(existing - desired):
            # Move retired public code under the private, bounded cleanup root.
            (root/proposal).chmod(0o755)
            os.rename(root/proposal, stage/("retired-" + proposal))
            fsync_dir(root)
            erase_private_stage(stage, owner)
            stage.mkdir(mode=0o700)
        return {"decision": "published", "proposals": sorted(desired), "created": len(published),
                "retired": len(existing-desired), "recovered_interrupted_stage": recovered,
                "authority": "local-source-publication-receipt", "production_authorized": False}
    finally:
        if stage.exists():
            erase_private_stage(stage, owner)
            fsync_dir(root)


def main():
    try:
        require(len(sys.argv) == 1 and os.getuid() == 0, "INVALID_INVOCATION")
        configuration = catalog(worker.parse(worker.checked_bytes(CATALOG, 16384)))
        result = reconcile(configuration)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except Refused as error:
        print(json.dumps({"decision": "reject", "code": str(error)}, separators=(",", ":")))
        return 2
    except Exception:
        print('{"decision":"reject","code":"SOURCE_STAGING_FAILED"}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
