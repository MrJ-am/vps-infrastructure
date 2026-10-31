#!/usr/bin/env python3
"""Export exact public Git code and checked Cargo inputs; no checkout or hooks."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tomllib

from prepare import REGISTRY, Refused, checked_bytes, crate_archive, crate_files, digest, put, regular_bytes


def verify(root, expected):
    record = json.loads(checked_bytes(root, "manifest.json", expected))
    if set(record) != {"schema_version", "source_commit", "source_tree", "source_blobs", "files", "cargo_packages"} or record["schema_version"] != 1:
        raise Refused("WORKER_MANIFEST_REFUSED")
    if not all(re.fullmatch(r"[a-f0-9]{40}", record[name]) for name in ("source_commit", "source_tree")):
        raise Refused("WORKER_REVISION_REFUSED")
    actual = set()
    for path in root.rglob("*"):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise Refused("WORKER_INPUT_TYPE_REFUSED")
        if path.is_file() and path != root / "manifest.json":
            actual.add(str(path.relative_to(root)))
    if actual != set(record["files"]):
        raise Refused("WORKER_INPUT_SET_CHANGED")
    if set(record["source_blobs"]) != {name for name in actual if name.startswith("source/")} or any(
        not name.startswith(("source/", "cargo-vendor/")) for name in actual
    ):
        raise Refused("WORKER_SOURCE_SET_CHANGED")
    for name, checksum in record["files"].items():
        value = checked_bytes(root, name, checksum)
        if name.startswith("source/"):
            blob = hashlib.sha1(b"blob " + str(len(value)).encode() + b"\0" + value).hexdigest()
            if record["source_blobs"].get(name) != blob:
                raise Refused("WORKER_SOURCE_BLOB_CHANGED")
    packages = [p for p in tomllib.loads(regular_bytes(root, "source/Cargo.lock").decode())["package"] if p.get("source")]
    if packages != record["cargo_packages"] or any(p["source"] != REGISTRY for p in packages):
        raise Refused("WORKER_CARGO_GRAPH_CHANGED")
    vendor_files = set()
    for package in packages:
        prefix = "cargo-vendor/" + package["name"] + "-" + package["version"] + "/"
        checksums = json.loads(regular_bytes(root, prefix + ".cargo-checksum.json"))
        if set(checksums) != {"package", "files"} or checksums["package"] != package["checksum"]:
            raise Refused("WORKER_CRATE_CHANGED")
        vendor_files.add(prefix + ".cargo-checksum.json")
        for name, checksum in checksums["files"].items():
            checked_bytes(root, prefix + name, checksum)
            vendor_files.add(prefix + name)
    if {n for n in actual if n.startswith("cargo-vendor/")} != vendor_files:
        raise Refused("WORKER_VENDOR_SET_CHANGED")
    return record


def materialize(repository, revision, vendor, cache, destination):
    if not re.fullmatch(r"[a-f0-9]{40}", revision):
        raise Refused("EXACT_WORKER_REVISION_REQUIRED")
    destination.mkdir(parents=True, exist_ok=False)
    def git(*args):
        environment = {"PATH": os.environ["PATH"], "LANG": "C", "LC_ALL": "C", "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_TERMINAL_PROMPT": "0", "GIT_NO_REPLACE_OBJECTS": "1"}
        return subprocess.check_output(["git", "-c", "core.hooksPath=/dev/null", "--no-replace-objects", "-C", str(repository), *args],
            env=environment, stdin=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
    tree = git("rev-parse", revision + "^{tree}").decode().strip()
    blobs = {}
    for item in git("ls-tree", "-r", "-z", revision).split(b"\0"):
        if not item:
            continue
        metadata, name = item.split(b"\t", 1)
        mode, kind, blob = metadata.decode().split()
        name = name.decode()
        selected = name in {"Cargo.toml", "Cargo.lock", "rust-toolchain.toml", "docs/outils.json", "docs/tutoriel.json", "docs/CONTRAT-SEANCE.md"} or (
            name.startswith(("src/", "tests/", "migrations/", "journal/", "workers/", "scripts/")) and name.endswith((".rs", ".sql", ".json")))
        if not selected:
            continue
        if kind != "blob" or mode not in {"100644", "100755"} or int(git("cat-file", "-s", blob)) > 16 * 1024**2:
            raise Refused("WORKER_SOURCE_REFUSED")
        raw = git("cat-file", "blob", blob)
        name = "source/" + name
        put(destination, name, raw)
        blobs[name] = blob
    packages = [p for p in tomllib.loads(regular_bytes(destination, "source/Cargo.lock").decode())["package"] if p.get("source")]
    for package in packages:
        if package["source"] != REGISTRY:
            raise Refused("WORKER_REGISTRY_REFUSED")
        prefix = package["name"] + "-" + package["version"]
        if (vendor / prefix).is_dir():
            checksums = json.loads(regular_bytes(vendor, prefix + "/.cargo-checksum.json"))
            if set(checksums) != {"package", "files"} or checksums["package"] != package["checksum"]:
                raise Refused("WORKER_REUSED_CRATE_CHANGED")
            files = {name: checked_bytes(vendor / prefix, name, checksum) for name, checksum in checksums["files"].items()}
            files[".cargo-checksum.json"] = regular_bytes(vendor, prefix + "/.cargo-checksum.json")
        else:
            files = crate_files(crate_archive(cache, package, True), package)
        for name, raw in files.items():
            put(destination, "cargo-vendor/" + prefix + "/" + name, raw)
    record = {"schema_version": 1, "source_commit": revision, "source_tree": tree, "source_blobs": blobs,
              "files": {str(path.relative_to(destination)): digest(path.read_bytes()) for path in sorted(destination.rglob("*")) if path.is_file()},
              "cargo_packages": packages}
    raw = (json.dumps(record, sort_keys=True, indent=2) + "\n").encode()
    put(destination, "manifest.json", raw)
    verify(destination, digest(raw))
    return {"decision": "prepared-not-qualified", "source_revision": revision, "source_files": len(blobs),
            "cargo_packages": len(packages), "manifest_sha256": digest(raw)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    check = sub.add_parser("verify")
    check.add_argument("root", type=Path)
    check.add_argument("sha256")
    prepare = sub.add_parser("prepare")
    prepare.add_argument("repository", type=Path)
    prepare.add_argument("revision")
    prepare.add_argument("vendor", type=Path)
    prepare.add_argument("cache", type=Path)
    prepare.add_argument("destination", type=Path)
    args = parser.parse_args()
    if args.operation == "verify":
        verify(args.root, args.sha256)
        print('{"decision":"verified-public-inputs"}')
    else:
        print(json.dumps(materialize(args.repository, args.revision, args.vendor, args.cache, args.destination)))


if __name__ == "__main__":
    main()
