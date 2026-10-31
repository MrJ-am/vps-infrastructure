#!/usr/bin/env python3
"""Prepare the exact, independently tested observation closure in Cloud only.

This producer never contacts a VPS, signs an approval or runs the observation.
It checks the recovered qualification and imports its export in a fresh local
store before producing delivery metadata. No Nix trust setting is relaxed.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from urllib.parse import quote


PACKAGE = "/nix/store/25rzj9i3jv9f1878dwgkysnc454ndr84-mrjam-observe-adoption-v2"
NAR_HASH = "sha256-y9318KAK+1X/f6Lo6bHTNgJJHn8AIKRQj+jNikgP5xo="
QUALIFICATION_SHA256 = "4f89ef0d01f5af7d93bdcc189f150bf8daf7ce99ff9eee821a9e2faa971ccac5"
EXPORT_NAME = "mrjam-observe-adoption-v2.nix-export"


def checksum(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run(*args: str, timeout: int = 180) -> bytes:
    return subprocess.check_output(args, timeout=timeout)


def path_info(store: str | None = None) -> dict:
    args = ["nix", "path-info", "--offline", "--json", "--recursive"]
    if store:
        args.extend(["--store", store])
    raw = json.loads(run(*args, PACKAGE))
    entries = raw if isinstance(raw, dict) else {entry["path"]: entry for entry in raw}
    return {path: {"nar_hash": value["narHash"], "nar_size": value["narSize"],
                   "references": sorted(value["references"])}
            for path, value in sorted(entries.items())}


def produce(qualification: Path, destination: Path) -> dict:
    if qualification.is_symlink() or checksum(qualification) != QUALIFICATION_SHA256:
        raise ValueError("QUALIFICATION_HASH_MISMATCH")
    evidence = json.loads(qualification.read_bytes())
    if evidence["overall_passed"] is not True or evidence["candidate_package"] != PACKAGE:
        raise ValueError("QUALIFICATION_NOT_PASSED")
    for filename, expected in evidence["source_sha256"].items():
        if checksum(Path(filename)) != expected:
            raise ValueError("QUALIFIED_SOURCE_CHANGED")
    if destination.exists() or destination.is_symlink():
        raise ValueError("NEW_DESTINATION_REQUIRED")
    closure = path_info()
    if len(closure) != 83 or closure[PACKAGE]["nar_hash"] != NAR_HASH:
        raise ValueError("QUALIFIED_CLOSURE_CHANGED")
    if any(set(entry["references"]) - set(closure) for entry in closure.values()):
        raise ValueError("INCOMPLETE_CLOSURE")
    run("nix", "store", "verify", "--offline", "--no-trust", "--recursive", PACKAGE)
    destination.mkdir(parents=True, mode=0o755)
    export_path = destination / EXPORT_NAME
    with export_path.open("xb") as output:
        subprocess.run(["nix-store", "--export", *sorted(closure)], stdout=output,
                       check=True, timeout=180)
    compressed = destination / (EXPORT_NAME + ".gz")
    with export_path.open("rb") as source, compressed.open("xb") as output:
        with gzip.GzipFile(filename="", fileobj=output, mode="wb", mtime=0) as stream:
            shutil.copyfileobj(source, stream)
    # The alternate local store cannot replace paths in the original store.
    # Import is a file transfer; it never runs an imported program.
    with tempfile.TemporaryDirectory(prefix="mrjam-observation-import-") as scratch:
        store = "local?root=" + quote(scratch, safe="/")
        with export_path.open("rb") as source:
            result = subprocess.run(["nix-store", "--store", store, "--import"],
                                    stdin=source, stdout=subprocess.PIPE,
                                    check=True, timeout=180)
        if set(result.stdout.decode().splitlines()) != set(closure):
            raise ValueError("IMPORTED_PATH_SET_MISMATCH")
        imported = path_info(store)
        if imported != closure:
            raise ValueError("IMPORTED_CLOSURE_MISMATCH")
        run("nix", "store", "verify", "--offline", "--no-trust", "--recursive",
            "--store", store, PACKAGE)
    manifest = {
        "schema_version": 1,
        "scope": "Exact qualified observation closure; no production activation",
        "package": PACKAGE, "package_nar_hash": NAR_HASH,
        "qualification_sha256": QUALIFICATION_SHA256,
        "closure": closure,
        "closure_paths": len(closure),
        "total_nar_bytes": sum(entry["nar_size"] for entry in closure.values()),
        "exports": {p.name: {"bytes": p.stat().st_size, "sha256": checksum(p)}
                    for p in (export_path, compressed)},
        "local_checks": {"qualification_sources_match": True,
                         "recursive_store_integrity": True,
                         "fresh_store_import_path_set": True,
                         "fresh_store_nar_hashes_sizes_references": True,
                         "fresh_store_recursive_integrity": True},
        "nix_version": run("nix", "--version").decode().strip(),
        "fresh_import_uid": os.geteuid(),
        "nix_trust_settings_modified": False,
        "production_observation_performed": False,
        "production_deployment_performed": False,
        "limitations": ["Local import does not establish the rights of Spectre's untrusted daemon client",
                        "No signature, protected approval or active VPS compatibility is inferred",
                        "Fresh import uses a separate local store, not the VPS store"]
    }
    (destination / "delivery-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return {"status": "exported_and_import_checked", "closure_paths": len(closure),
            "total_nar_bytes": manifest["total_nar_bytes"], "exports": manifest["exports"],
            "manifest_sha256": checksum(destination / "delivery-manifest.json")}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qualification", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(produce(args.qualification, args.destination), sort_keys=True))
