#!/usr/bin/env python3
"""Cloud producer only: verified delta and fresh-store import, no VPS access."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

INFRA = Path(__file__).resolve().parents[2]
BASE_MANIFEST_SHA256 = "04c0dc51cbe4ca88daac24a180ccb8c19ae71781a36e0de07581e686f5b9d7d8"
NAME = "mrjam-observe-services-v1.nix-export"
NIX = ["nix", "--extra-experimental-features", "nix-command"]


def checksum(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run(argv, **kwargs):
    return subprocess.run(argv, stdin=kwargs.pop("stdin", subprocess.DEVNULL),
                          stdout=kwargs.pop("stdout", subprocess.PIPE),
                          stderr=subprocess.PIPE, check=True, timeout=300, **kwargs)


def closure(package, store=None):
    argv = [*NIX, "path-info", "--offline", "--json", "--json-format", "1", "--recursive"]
    if store:
        argv += ["--store", store]
    result = json.loads(run([*argv, package]).stdout)
    return {path: {"nar_hash": item["narHash"], "nar_size": item["narSize"],
                   "references": sorted(item["references"])}
            for path, item in sorted(result.items())}


def import_gzip(path, store):
    # The compressed and uncompressed checksums are checked before this call.
    with subprocess.Popen(["gzip", "--decompress", "--stdout", str(path)],
                          stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL) as source:
        imported = run(["nix-store", "--store", store, "--import"], stdin=source.stdout)
        source.stdout.close()
        if source.wait(timeout=30) != 0:
            raise ValueError("DECOMPRESSION_FAILED")
    return imported.stdout.decode().splitlines()


def produce(qualification, base_export, destination):
    evidence = json.loads(qualification.read_bytes())
    if evidence["overall_passed"] is not True or len(evidence["groups_passed"]) != 5:
        raise ValueError("SYSTEM_QUALIFICATION_REQUIRED")
    for filename, expected in evidence["source_sha256"].items():
        if checksum(INFRA / filename) != expected:
            raise ValueError("QUALIFIED_SOURCE_CHANGED")
    package = evidence["candidate_package"]
    manifest_path = INFRA / "operations/bootstrap-observation/delivery-manifest-20261031.json"
    if checksum(manifest_path) != BASE_MANIFEST_SHA256:
        raise ValueError("ORIGINAL_MANIFEST_MISMATCH")
    original = json.loads(manifest_path.read_bytes())
    compressed_expected = original["exports"]["mrjam-observe-adoption-v2.nix-export.gz"]
    if (base_export.is_symlink() or base_export.stat().st_size != compressed_expected["bytes"]
            or checksum(base_export) != compressed_expected["sha256"]):
        raise ValueError("ORIGINAL_EXPORT_MISMATCH")
    with gzip.open(base_export, "rb") as stream:
        raw_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    if raw_hash != original["exports"]["mrjam-observe-adoption-v2.nix-export"]["sha256"]:
        raise ValueError("ORIGINAL_DECOMPRESSED_EXPORT_MISMATCH")
    expected = closure(package)
    delta_paths = sorted(set(expected) - set(original["closure"]))
    if (package not in delta_paths or expected[package]["nar_hash"] != evidence["candidate_nar_hash"]
            or any(set(item["references"]) - set(expected) for item in expected.values())):
        raise ValueError("CANDIDATE_CLOSURE_MISMATCH")
    for path in set(expected) & set(original["closure"]):
        if expected[path] != original["closure"][path]:
            raise ValueError("ORIGINAL_DEPENDENCY_CHANGED")
    run([*NIX, "store", "verify", "--offline", "--no-trust", "--recursive", package])
    if destination.exists() or destination.is_symlink():
        raise ValueError("NEW_DESTINATION_REQUIRED")
    destination.mkdir(parents=True, mode=0o755)
    delta = destination / NAME
    with delta.open("xb") as output:
        run(["nix-store", "--export", *delta_paths], stdout=output)
    compressed = destination / (NAME + ".gz")
    with delta.open("rb") as source, compressed.open("xb") as output:
        with gzip.GzipFile(filename="", fileobj=output, mode="wb", mtime=0) as stream:
            shutil.copyfileobj(source, stream)
    with tempfile.TemporaryDirectory(prefix="mrjam-services-import-") as temporary:
        store = "local?root=" + temporary
        if set(import_gzip(base_export, store)) != set(original["closure"]):
            raise ValueError("BASE_IMPORT_PATHS_DIFFER")
        imported = import_gzip(compressed, store)
        if (len(imported) != len(delta_paths) or set(imported) != set(delta_paths)
                or closure(package, store) != expected):
            raise ValueError("DELTA_IMPORT_CLOSURE_DIFFERS")
        run([*NIX, "store", "verify", "--offline", "--no-trust", "--recursive", "--store", store, package])
    result = {
        "schema_version": 1, "scope": "Human-only service/code observation; original runtime dependencies required",
        "package": package, "package_nar_hash": evidence["candidate_nar_hash"],
        "qualification_sha256": checksum(qualification),
        "base_manifest_sha256": BASE_MANIFEST_SHA256,
        "exports": {p.name: {"bytes": p.stat().st_size, "sha256": checksum(p)} for p in (delta, compressed)},
        "exported_paths": delta_paths, "closure": expected, "closure_paths": len(expected),
        "total_nar_bytes": sum(item["nar_size"] for item in expected.values()),
        "local_checks": {"qualified_sources_match": True, "original_dependencies_unchanged": True,
                         "recursive_content_verified": True, "fresh_store_base_then_delta_import": True,
                         "fresh_store_entire_closure_matches": True, "fresh_store_recursive_content_verified": True},
        "fresh_import_uid": os.geteuid(), "production_access": False,
        "production_activation": False, "nix_trust_settings_modified": False,
        "limitations": ["Delta requires the original closure", "Local qualification is not protected approval",
                        "Observed code metadata is not an authenticated running-build attestation"],
    }
    (destination / "delivery-manifest-services-20261101.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return {"package": package, "export": result["exports"][compressed.name],
            "closure_paths": len(expected), "exported_paths": len(delta_paths), "fresh_import_passed": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qualification", required=True, type=Path)
    parser.add_argument("--base-export", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(produce(args.qualification, args.base_export, args.destination), sort_keys=True))
