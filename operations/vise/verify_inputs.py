#!/usr/bin/env python3
"""Verify the exact reviewed materialization, before any build script executes."""
import argparse
import hashlib
import json
import os
from pathlib import Path


def file_inventory(root, *, exclude_manifest=False):
    result = {}
    for path in sorted(root.rglob("*")):
        name = path.relative_to(root).as_posix()
        if exclude_manifest and name == "materialization.json":
            continue
        if path.is_symlink():
            target = os.readlink(path)
            if os.path.isabs(target) or not path.resolve().is_relative_to(root.resolve()):
                raise ValueError("INPUT_LINK_ESCAPES_ROOT")
            if not path.resolve().is_file():
                raise ValueError("INPUT_LINK_NOT_FILE")
            result[name] = {"link": target}
        elif path.is_file():
            result[name] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                            "executable": bool(path.stat().st_mode & 0o111)}
        elif not path.is_dir():
            raise ValueError("INPUT_SPECIAL_FILE")
    return result


def verify(root, expected, source_lock):
    manifest_path = root / "materialization.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError("MANIFEST_TYPE_REFUSED")
    raw = manifest_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("MANIFEST_HASH_MISMATCH")
    manifest = json.loads(raw)
    if hashlib.sha256(source_lock.read_bytes()).hexdigest() != manifest["source_selection_sha256"]:
        raise ValueError("SOURCE_SELECTION_MISMATCH")
    if file_inventory(root, exclude_manifest=True) != manifest["files"]:
        raise ValueError("INPUT_CONTENT_MISMATCH")
    lock = json.loads(source_lock.read_bytes())
    if (manifest["revision"] != lock["revision"] or manifest["repository"] != lock["repository"]
            or manifest["npm_lifecycle_scripts"] is not False):
        raise ValueError("SOURCE_IDENTITY_MISMATCH")
    for name, wanted in lock["files"].items():
        path = root / "source" / name
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != wanted["sha256"]:
            raise ValueError("SOURCE_CONTENT_MISMATCH")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--source-lock", type=Path, required=True)
    args = parser.parse_args()
    verify(args.inputs, args.manifest_sha256, args.source_lock)
