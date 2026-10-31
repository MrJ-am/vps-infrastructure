#!/usr/bin/env python3
"""Export a local public-code Nix fixture; never installed on a production host.

Run only in the existing offline synthetic Nix container. Configuration and
source inputs must be under the local build area. Every exported store path is
verified by Nix, then its NAR hash is checked again after copying. Source files
are copied only from the closed manifest, with no symlink traversal.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys

spec = importlib.util.spec_from_file_location("worker", Path(__file__).parents[1] / "worker.py")
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
BUILD = Path("/workspace/shared/mrjam-declarative-build")
EXPORT = Path("/workspace/shared/mrjam-declarative-nix")


def require(value, code):
    if not value:
        raise RuntimeError(code)


def nix(arguments):
    result = subprocess.run(arguments, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=180)
    require(result.returncode == 0 and len(result.stdout) <= 1048576, "NIX_VERIFICATION_FAILED")
    return result.stdout.decode("ascii").strip()


def nar_hash(path):
    value = nix(["nix", "hash", "path", "--type", "sha256", "--sri", str(path)])
    require(re.fullmatch(r"sha256-[A-Za-z0-9+/]{43}=", value), "INVALID_NAR_HASH")
    return value


def main():
    require(len(sys.argv) == 4 and os.getuid() == 0 and os.environ.get("MRJAM_SYNTHETIC_CONTAINER") == "1"
            and set(os.listdir("/sys/class/net")) == {"lo"}, "OFFLINE_SYNTHETIC_CONTAINER_REQUIRED")
    config_path, source = (Path(argument).absolute() for argument in sys.argv[1:3])
    name = sys.argv[3]
    require(config_path.is_relative_to(BUILD) and source.is_relative_to(BUILD)
            and re.fullmatch(r"worker-[A-Za-z0-9_-]+", name), "INVALID_FIXTURE_PATH")
    for candidate in (config_path, source):
        for parent in (candidate, *candidate.parents):
            require(not parent.is_symlink(), "SYMLINK_REFUSED")
    require(config_path.stat().st_size <= 4096, "CONFIGURATION_LIMIT")
    configuration = worker.policy(worker.parse(config_path.read_bytes()))
    paths = worker.closure(Path(configuration["closure_file"]).read_bytes(), configuration["validator_store"])
    require(configuration["bubblewrap_store"] in paths, "INCOMPLETE_VALIDATOR_CLOSURE")
    require((source / "manifest.json").is_file() and not (source / "manifest.json").is_symlink()
            and (source / "manifest.json").stat().st_size <= worker.MAX_MANIFEST, "INVALID_SOURCE_MANIFEST")
    raw = (source / "manifest.json").read_bytes()
    manifest = worker.parse(raw)
    worker.exact(manifest, ("schema_version", "rules_revision", "files"))
    require(manifest["schema_version"] == 1 and type(manifest["schema_version"]) is int
            and manifest["rules_revision"] == configuration["rules_revision"]
            and type(manifest["files"]) is list and 0 < len(manifest["files"]) <= worker.MAX_FILES, "INVALID_SOURCE_MANIFEST")
    total = 0
    names = set()
    for entry in manifest["files"]:
        worker.exact(entry, ("path", "bytes", "sha256"))
        relative = entry["path"]
        require(type(relative) is str and re.fullmatch(r"[A-Za-z0-9._+~/-]{1,300}", relative)
                and not relative.startswith("/") and str(PurePosixPath(relative)) == relative
                and all(part not in (".", "..") for part in PurePosixPath(relative).parts)
                and relative != "manifest.json" and relative not in names, "INVALID_SOURCE_PATH")
        names.add(relative)
        require(type(entry["bytes"]) is int and 0 <= entry["bytes"] <= worker.MAX_INPUT
                and type(entry["sha256"]) is str and worker.HEX.fullmatch(entry["sha256"]), "INVALID_SOURCE_FILE")
        total += entry["bytes"]
        require(total <= worker.MAX_INPUT, "SOURCE_LIMIT")
    root = EXPORT / name
    root.mkdir(mode=0o755) # No overwrite of an earlier fixture or receipt.
    (root / "nix/store").mkdir(parents=True)
    proposal = hashlib.sha256(raw).hexdigest()
    target = root / "input" / proposal
    target.mkdir(parents=True)
    for entry in manifest["files"]:
        origin = source / entry["path"]
        for parent in (origin, *origin.parents):
            require(not parent.is_symlink(), "SYMLINK_REFUSED")
            if parent == source:
                break
        meta = os.lstat(origin)
        require(stat.S_ISREG(meta.st_mode) and meta.st_nlink == 1 and meta.st_size == entry["bytes"], "INVALID_SOURCE_FILE")
        destination = target / entry["path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        hashed = hashlib.sha256()
        fd = os.open(origin, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream, destination.open("xb") as output:
            size = 0
            while block := stream.read(1024 * 1024):
                size += len(block)
                require(size <= entry["bytes"], "SOURCE_CHANGED")
                hashed.update(block)
                output.write(block)
        require(size == entry["bytes"] and hashed.hexdigest() == entry["sha256"], "SOURCE_HASH_MISMATCH")
        destination.chmod(0o555 if meta.st_mode & 0o111 else 0o444)
    (target / "manifest.json").write_bytes(raw)
    (target / "manifest.json").chmod(0o444)
    for base, directories, _ in os.walk(root / "input", topdown=False):
        Path(base).chmod(0o555)
    worker.verify_input(root / "input", proposal, configuration["rules_revision"])
    records = []
    require(shutil.disk_usage(root).free >= 2 * 1024**3, "INSUFFICIENT_FIXTURE_SPACE")
    for path in paths:
        nix(["nix-store", "--verify-path", path])
        expected = nar_hash(path)
        destination = root / path.removeprefix("/")
        if Path(path).is_dir():
            shutil.copytree(path, destination, symlinks=True)
        else:
            shutil.copy2(path, destination, follow_symlinks=False)
        require(nar_hash(destination) == expected, "COPIED_CLOSURE_HASH_MISMATCH")
        records.append({"path": path, "nar_hash": expected, "verified_after_copy": True})
        require(shutil.disk_usage(root).free >= 1024**3, "INSUFFICIENT_FIXTURE_SPACE")
    record = {"schema_version": 1, "scope": "local-public-code-fixture", "configuration": configuration,
              "proposal_sha256": proposal, "paths": records}
    encoded = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("ascii") + b"\n"
    (root / "export.json").write_bytes(encoded)
    (root / "export.json").chmod(0o444)
    (root / "nix/store").chmod(0o555)
    (root / "nix").chmod(0o555)
    root.chmod(0o555)
    print(json.dumps({"decision": "exported", "scope": "local-public-code-fixture", "fixture": name,
                      "proposal_sha256": proposal, "export_sha256": hashlib.sha256(encoded).hexdigest(), "store_paths": len(paths)}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        code = str(error) if type(error) in (RuntimeError, worker.Refused) and re.fullmatch(r"[A-Z_]+", str(error)) else "EXPORT_FAILED"
        print(json.dumps({"decision": "failed", "code": code}))
        raise SystemExit(1)
