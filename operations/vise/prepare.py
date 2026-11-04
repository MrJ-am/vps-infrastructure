#!/usr/bin/env python3
"""Prepare only pinned, public ViSe build inputs; never contact the VPS.

The source revision is a build proposal, not a claim about the installed binary.
Cargo archive integrity and extraction use the already reviewed build helper.
npm lifecycle scripts, audit and funding requests are disabled.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib

HERE = Path(__file__).resolve().parent
from verify_inputs import file_inventory
sys.path.insert(0, str(HERE.parent / "builds"))
import prepare as cargo_inputs  # noqa: E402


def prepare(source, cargo_cache, elm_home, destination, npm_cache, download):
    # npm runs inside destination/source; its cache must not become source input.
    destination, npm_cache = destination.absolute(), npm_cache.absolute()
    lock_bytes = (HERE / "sources.lock.json").read_bytes()
    lock = json.loads(lock_bytes)
    if cargo_inputs.git(source, "rev-parse", "HEAD") != lock["revision"]:
        raise ValueError("SOURCE_REVISION_MISMATCH")
    files = {}
    for name, expected in lock["files"].items():
        value = cargo_inputs.checked_bytes(source, name, expected["sha256"])
        if len(value) != expected["bytes"]:
            raise ValueError("SOURCE_LENGTH_MISMATCH")
        files[name] = value
    npm_lock = json.loads(files["package-lock.json"])
    for name, package in npm_lock["packages"].items():
        if name and (not package.get("resolved", "").startswith("https://registry.npmjs.org/")
                     or not package.get("integrity", "").startswith("sha512-")):
            raise ValueError("NPM_ORIGIN_OR_INTEGRITY_REFUSED")
    cargo = tomllib.loads(files["backend/Cargo.lock"].decode())
    dependencies = [p for p in cargo["package"] if p.get("source")]
    if any(p["source"] != cargo_inputs.REGISTRY for p in dependencies):
        raise ValueError("CARGO_ORIGIN_REFUSED")
    elm_lock_bytes = (HERE.parent / "builds/elm-dependencies.lock.json").read_bytes()
    elm_lock = json.loads(elm_lock_bytes)
    required = {}
    for section in json.loads(files["elm.json"])["dependencies"].values():
        required.update(section)
    if any(elm_lock["packages"].get(name, {}).get("version") != version for name, version in required.items()):
        raise ValueError("ELM_CONTENT_LOCK_MISMATCH")
    if destination.exists() or destination.is_symlink() or npm_cache.exists():
        raise ValueError("NEW_DESTINATIONS_REQUIRED")
    destination.mkdir(parents=True)
    for name, value in files.items():
        cargo_inputs.put(destination / "source", name, value)
    for dependency in dependencies:
        data = cargo_inputs.crate_archive(cargo_cache, dependency, download)
        for name, value in cargo_inputs.crate_files(data, dependency).items():
            cargo_inputs.put(destination / "cargo-vendor", f"{dependency['name']}-{dependency['version']}/{name}", value)
    packages = elm_home / "0.19.1/packages"
    cargo_inputs.put(destination / "elm-home/0.19.1/packages", "registry.dat",
                     cargo_inputs.checked_bytes(HERE.parent / "builds", "elm-registry.dat", elm_lock["registry_sha256"]))
    for name, version in required.items():
        for filename, checksum in elm_lock["packages"][name]["files"].items():
            cargo_inputs.put(destination / "elm-home/0.19.1/packages" / name / version, filename,
                             cargo_inputs.checked_bytes(packages / name / version, filename, checksum))
    # Only the pinned public registry is admissible. No deployment script runs.
    subprocess.run(["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund",
                    "--registry=https://registry.npmjs.org", "--cache=" + str(npm_cache)],
                   cwd=destination / "source", check=True, timeout=600,
                   stdin=subprocess.DEVNULL)
    shutil.move(destination / "source/node_modules", destination / "node_modules")
    manifest = {
        "schema_version": 1, "repository": lock["repository"], "revision": lock["revision"],
        "source_selection_sha256": hashlib.sha256(lock_bytes).hexdigest(),
        "elm_content_lock_sha256": hashlib.sha256(elm_lock_bytes).hexdigest(),
        "cargo_registry_packages": len(dependencies), "elm_packages": len(required),
        "npm_lifecycle_scripts": False, "files": file_inventory(destination),
        "production_qualification": False,
    }
    cargo_inputs.put(destination, "materialization.json", (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode())
    return {"files": len(manifest["files"]), "cargo_packages": len(dependencies),
            "manifest_sha256": hashlib.sha256((destination / "materialization.json").read_bytes()).hexdigest()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("source", "cargo-cache", "elm-home", "destination", "npm-cache"):
        parser.add_argument("--" + option, required=True, type=Path)
    parser.add_argument("--download-missing", action="store_true")
    args = parser.parse_args()
    print(json.dumps(prepare(args.source, args.cargo_cache, args.elm_home,
                             args.destination, args.npm_cache, args.download_missing)))
