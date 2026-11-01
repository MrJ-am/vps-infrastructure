#!/usr/bin/env python3
"""Reuse verified dependencies only when all three dependency locks are identical.

The old selection/manifest remain unchanged. The new source is independently
checked against its own versioned selection; no arbitrary checkout file enters.
Hardlinks save local disk space; these preparation directories must have no
concurrent writer. Nix verifies again before building in a separate directory.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

HERE = Path(__file__).resolve().parent
from verify_inputs import file_inventory, verify
sys.path.insert(0, str(HERE.parent / "builds"))
import prepare as inputs

BASELINE_MANIFEST = "f119430d6c3163faece432c1c4cc84449f3e9cd0ffc9866b2136f9b4dcccdfc6"


def prepare(baseline, source, destination):
    verify(baseline, BASELINE_MANIFEST, HERE / "sources.lock.json")
    old = json.loads((HERE / "sources.lock.json").read_bytes())
    lock_bytes = (HERE / "sources-adoption-20261101.lock.json").read_bytes()
    lock = json.loads(lock_bytes)
    if inputs.git(source, "rev-parse", "HEAD") != lock["revision"]:
        raise ValueError("SOURCE_REVISION_MISMATCH")
    if set(lock["files"]) != set(old["files"]):
        raise ValueError("SOURCE_SET_CHANGED")
    for path in ("backend/Cargo.toml", "backend/Cargo.lock", "elm.json", "package.json", "package-lock.json"):
        if lock["files"][path] != old["files"][path]:
            raise ValueError("DEPENDENCY_REUSE_REFUSED")
    sources = {name: inputs.checked_bytes(source, name, wanted["sha256"])
               for name, wanted in lock["files"].items()}
    if destination.exists() or destination.is_symlink():
        raise ValueError("NEW_DESTINATION_REQUIRED")
    destination.mkdir(parents=True)
    for name, data in sources.items():
        inputs.put(destination / "source", name, data)
    for directory in ("cargo-vendor", "elm-home", "node_modules"):
        shutil.copytree(baseline / directory, destination / directory,
                        symlinks=True, copy_function=os.link)
    manifest = json.loads((baseline / "materialization.json").read_bytes())
    manifest.update(revision=lock["revision"],
                    source_selection_sha256=hashlib.sha256(lock_bytes).hexdigest(),
                    files=file_inventory(destination),
                    dependency_reuse_from_manifest_sha256=BASELINE_MANIFEST)
    raw = (json.dumps(manifest,indent=2,sort_keys=True) + "\n").encode()
    inputs.put(destination, "materialization.json", raw)
    expected = hashlib.sha256(raw).hexdigest()
    verify(destination, expected, HERE / "sources-adoption-20261101.lock.json")
    return {"manifest_sha256": expected, "revision": lock["revision"], "files": len(manifest["files"])}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("baseline", "source", "destination"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.baseline, args.source, args.destination)))
