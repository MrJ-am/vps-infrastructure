#!/usr/bin/env python3
"""Verify the exact source selection and every vendored dependency before build."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import tomllib

from prepare import HERE, REGISTRY, Refused, checked_bytes, digest


def verify(root: Path, expected_manifest_sha256: str) -> dict:
    manifest_bytes = checked_bytes(root, "materialization.json", expected_manifest_sha256)
    manifest = json.loads(manifest_bytes)
    sources_bytes = (HERE / "sources.lock.json").read_bytes()
    elm_bytes = (HERE / "elm-dependencies.lock.json").read_bytes()
    sources, elm = json.loads(sources_bytes), json.loads(elm_bytes)
    if manifest["source_selection_sha256"] != digest(sources_bytes) or manifest["elm_dependency_lock_sha256"] != digest(elm_bytes):
        raise Refused("BUILD_LOCK_MISMATCH")
    if manifest["source_commits"] != {name: value["commit"] for name, value in sources["sources"].items()}:
        raise Refused("BUILD_COMMITS_MISMATCH")
    if manifest["deployment_authorized"] is not False:
        raise Refused("BUILD_APPROVAL_FIELD_REFUSED")
    expected = {}
    for key, specification in sources["sources"].items():
        for name, checksum in specification["files"].items():
            target = name if key == "platform" else f"components/{key}/{name}"
            target = "mateval-frontend/" + name.removeprefix("frontend/") if name.startswith("frontend/") else "platform-source/" + target
            expected[target] = checksum
    style_path = "mateval-frontend/style-mrjam.json"
    style = json.loads(checked_bytes(root, style_path, expected[style_path]))
    if style["revision"] != manifest["style_revision"]:
        raise Refused("BUILD_STYLE_MISMATCH")
    expected.update({"style-source/" + name: value for name, value in style["fichiers"].items()})
    expected["elm-home/0.19.1/packages/registry.dat"] = elm["registry_sha256"]
    for name, package in elm["packages"].items():
        for filename, checksum in package["files"].items():
            expected[f"elm-home/0.19.1/packages/{name}/{package['version']}/{filename}"] = checksum
    if manifest["source_files_sha256"] != expected:
        raise Refused("BUILD_SOURCE_SET_MISMATCH")
    for name, checksum in expected.items():
        checked_bytes(root, name, checksum)
    cargo = tomllib.loads((root / "platform-source/Cargo.lock").read_text())
    packages = [p for p in cargo["package"] if p.get("source")]
    if any(p["source"] != REGISTRY for p in packages):
        raise Refused("BUILD_REGISTRY_REFUSED")
    if manifest["cargo_registry_packages"] != [{"name": p["name"], "version": p["version"], "sha256": p["checksum"]} for p in packages]:
        raise Refused("BUILD_CRATE_SET_MISMATCH")
    checksums = manifest["cargo_vendor_checksum_files_sha256"]
    checksum_paths = {f"cargo-vendor/{p['name']}-{p['version']}/.cargo-checksum.json" for p in packages}
    if set(checksums) != checksum_paths:
        raise Refused("BUILD_VENDOR_SET_MISMATCH")
    all_files = set(expected) | {"materialization.json", "platform-source/materialization.json"}
    checked_bytes(root, "platform-source/materialization.json", expected_manifest_sha256)
    for package in packages:
        prefix = f"cargo-vendor/{package['name']}-{package['version']}/"
        checksum_path = prefix + ".cargo-checksum.json"
        checksum = json.loads(checked_bytes(root, checksum_path, checksums[checksum_path]))
        if set(checksum) != {"package", "files"} or checksum["package"] != package["checksum"]:
            raise Refused("BUILD_VENDOR_CHECKSUM_MISMATCH")
        all_files.add(checksum_path)
        for name, value in checksum["files"].items():
            checked_bytes(root, prefix + name, value)
            all_files.add(prefix + name)
    actual_files = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise Refused("BUILD_SYMLINK_REFUSED")
        if path.is_file():
            actual_files.add(path.relative_to(root).as_posix())
        elif not path.is_dir():
            raise Refused("BUILD_FILE_TYPE_REFUSED")
    if actual_files != all_files:
        raise Refused("BUILD_UNEXPECTED_FILE")
    return {"status": "verified", "source_files": len(expected), "cargo_packages": len(packages), "total_files": len(all_files)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    arguments = parser.parse_args()
    try:
        result = verify(arguments.inputs, arguments.manifest_sha256)
    except Exception as error:
        print(json.dumps({"status": "refused", "code": str(error) if isinstance(error, Refused) else "BUILD_INPUT_VERIFICATION_FAILED"}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
