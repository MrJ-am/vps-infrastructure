#!/usr/bin/env python3
"""Cloud-only producer: export the qualified new root, reuse the original closure.

No VPS operation or observation. An original export seeds a fresh isolated store
before the delta is imported and the entire new closure is compared and verified.
The original delivery and its expected hashes are never modified.
"""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

OPERATIONS = Path(__file__).resolve().parent.parent
BASE_MANIFEST_SHA256 = "04c0dc51cbe4ca88daac24a180ccb8c19ae71781a36e0de07581e686f5b9d7d8"
BASE_EXPORT_SHA256 = "a698f4460d919ad9c4bd61de216aad17c8d9c354107934957d51e2642cfa6114"
NAME = "mrjam-observe-provenance-v1.nix-export"
NIX = ["nix", "--extra-experimental-features", "nix-command"]


def checksum(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run(argv, **kwargs):
    return subprocess.run(argv, stdin=kwargs.pop("stdin", subprocess.DEVNULL),
                          stdout=kwargs.pop("stdout", subprocess.PIPE),
                          stderr=subprocess.PIPE, check=True, timeout=180, **kwargs)


def closure(package, store=None):
    argv = [*NIX, "path-info", "--offline", "--json", "--json-format", "2", "--recursive"]
    if store:
        argv += ["--store", store]
    result = json.loads(run([*argv, package]).stdout)
    if isinstance(result, list):
        result = {item["path"]: item for item in result}
    return {path: {"nar_hash": item["narHash"], "nar_size": item["narSize"],
                   "references": sorted(item["references"])}
            for path, item in sorted(result.items())}


def produce(qualification, base_export, destination):
    evidence = json.loads(qualification.read_bytes())
    if evidence["overall_passed"] is not True or len(evidence["groups_passed"]) != 8:
        raise ValueError("SYSTEM_QUALIFICATION_REQUIRED")
    for filename, expected in evidence["source_sha256"].items():
        if checksum(Path(filename)) != expected:
            raise ValueError("QUALIFIED_SOURCE_CHANGED")
    package = evidence["candidate_package"]
    expected_nar = evidence["candidate_nar_hash"]
    manifest_path = OPERATIONS / "bootstrap-observation/delivery-manifest-20261031.json"
    if checksum(manifest_path) != BASE_MANIFEST_SHA256 or checksum(base_export) != BASE_EXPORT_SHA256:
        raise ValueError("ORIGINAL_DELIVERY_MISMATCH")
    original = json.loads(manifest_path.read_bytes())
    expected = closure(package)
    if (set(expected) - set(original["closure"]) != {package}
            or expected[package]["nar_hash"] != expected_nar
            or any(set(item["references"]) - set(expected) for item in expected.values())):
        raise ValueError("DELTA_IS_NOT_ONE_QUALIFIED_ROOT")
    for path in set(expected) & set(original["closure"]):
        if expected[path] != original["closure"][path]:
            raise ValueError("ORIGINAL_DEPENDENCY_CHANGED")
    run([*NIX, "store", "verify", "--offline", "--no-trust", "--recursive", package])
    if destination.exists() or destination.is_symlink():
        raise ValueError("NEW_DESTINATION_REQUIRED")
    destination.mkdir(parents=True, mode=0o755)
    delta = destination / NAME
    with delta.open("xb") as output:
        run(["nix-store", "--export", package], stdout=output)
    compressed = destination / (NAME + ".gz")
    with delta.open("rb") as source, compressed.open("xb") as output:
        with gzip.GzipFile(filename="", fileobj=output, mode="wb", mtime=0) as stream:
            shutil.copyfileobj(source, stream)
    with tempfile.TemporaryDirectory(prefix="mrjam-provenance-import-") as temporary:
        store = "local?root=" + temporary
        with base_export.open("rb") as source:
            seeded = run(["nix-store", "--store", store, "--import"], stdin=source)
        if set(seeded.stdout.decode().splitlines()) != set(original["closure"]):
            raise ValueError("BASE_IMPORT_PATHS_DIFFER")
        with delta.open("rb") as source:
            imported = run(["nix-store", "--store", store, "--import"], stdin=source)
        if imported.stdout.decode().splitlines() != [package] or closure(package, store) != expected:
            raise ValueError("DELTA_IMPORT_CLOSURE_DIFFERS")
        run([*NIX, "store", "verify", "--offline", "--no-trust", "--recursive", "--store", store, package])
    result = {
        "schema_version": 1, "scope": "Qualified provenance observation root; original runtime dependencies required",
        "package": package, "package_nar_hash": expected_nar,
        "qualification_sha256": checksum(qualification),
        "base_manifest_sha256": BASE_MANIFEST_SHA256,
        "exports": {path.name: {"bytes": path.stat().st_size, "sha256": checksum(path)} for path in (delta, compressed)},
        "exported_paths": [package], "closure": expected, "closure_paths": len(expected),
        "total_nar_bytes": sum(item["nar_size"] for item in expected.values()),
        "local_checks": {"qualified_sources_match": True, "original_dependencies_unchanged": True,
                         "recursive_content_verified": True, "fresh_store_base_then_delta_import": True,
                         "fresh_store_entire_closure_matches": True, "fresh_store_recursive_content_verified": True},
        "fresh_import_uid": os.geteuid(), "production_access": False,
        "production_activation": False, "nix_trust_settings_modified": False,
        "limitations": ["Delta alone is not a complete closure", "Local qualification is not protected approval",
                        "No production source revision has been observed by Cloud"],
    }
    (destination / "delivery-manifest-provenance-20261031.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return {"package": package, "export": result["exports"][compressed.name],
            "closure_paths": len(expected), "fresh_import_passed": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qualification", required=True, type=Path)
    parser.add_argument("--base-export", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(produce(args.qualification, args.base_export, args.destination), sort_keys=True))
