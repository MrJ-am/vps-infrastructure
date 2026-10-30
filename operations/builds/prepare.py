#!/usr/bin/env python3
"""Materialize pinned, allowlisted source inputs; never build or contact a VPS.

Public crate downloads are optional and verified against Cargo.lock before use.
Nix builds consume the resulting directories without using a network or cache.
"""
from __future__ import annotations

import argparse
import errno
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import tarfile
import tomllib
import urllib.request

HERE = Path(__file__).resolve().parent
REGISTRY = "registry+https://github.com/rust-lang/crates.io-index"


class Refused(ValueError):
    pass


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def relative(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if not name or path.is_absolute() or any(p in ("", ".", "..") for p in name.split("/")):
        raise Refused("SOURCE_PATH_REFUSED")
    return path


def directory_descriptor(root: Path) -> int:
    """Return a directory opened from / without following ancestor symlinks."""
    parts = root.absolute().parts
    if parts[0] != "/" or any(part in (".", "..") for part in parts[1:]):
        raise Refused("SOURCE_PATH_REFUSED")
    directory = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for part in parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory)
            os.close(directory)
            directory = child
        return directory
    except Exception as error:
        os.close(directory)
        if isinstance(error, OSError) and error.errno in (errno.ELOOP, errno.ENOTDIR):
            raise Refused("SOURCE_SYMLINK_REFUSED") from None
        raise


def regular_bytes(root: Path, name: str, limit: int = 64 * 1024 * 1024) -> bytes:
    """Read a bounded regular file, without blocking on FIFO or following links."""
    full = root / relative(name)
    directory = directory_descriptor(full.parent)
    try:
        descriptor = os.open(full.name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory)
        with os.fdopen(descriptor, "rb") as source:
            metadata = os.fstat(source.fileno())
            if not stat.S_ISREG(metadata.st_mode):
                raise Refused("SOURCE_FILE_TYPE_REFUSED")
            if metadata.st_size > limit:
                raise Refused("SOURCE_SIZE_LIMIT")
            value = source.read(limit + 1)
            if len(value) > limit:
                raise Refused("SOURCE_SIZE_LIMIT")
            return value
    except OSError as error:
        if error.errno in (errno.ELOOP, errno.ENOTDIR):
            raise Refused("SOURCE_SYMLINK_REFUSED") from None
        raise
    finally:
        os.close(directory)


def checked_bytes(root: Path, name: str, expected: str) -> bytes:
    value = regular_bytes(root, name)
    if digest(value) != expected:
        raise Refused("SOURCE_HASH_MISMATCH")
    return value


def put(root: Path, name: str, value: bytes):
    target = root.joinpath(*relative(name).parts)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as handle:
        handle.write(value)
    target.chmod(0o644)


def git(root: Path, *arguments: str) -> str:
    environment = {"PATH": os.environ["PATH"], "LANG": "C", "LC_ALL": "C", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_TERMINAL_PROMPT": "0"}
    return subprocess.check_output(
        ["git", "-c", "core.hooksPath=/dev/null", "-C", str(root), *arguments],
        stderr=subprocess.DEVNULL, env=environment, timeout=20, text=True,
    ).strip()


def verify_sources(platform: Path, lock: dict) -> dict[str, bytes]:
    roots = {"platform": platform, "vision": platform / "components/vision", "mateval": platform / "components/mateval"}
    result = {}
    for key, specification in lock["sources"].items():
        root = roots[key]
        if git(root, "rev-parse", "HEAD") != specification["commit"]:
            raise Refused("SOURCE_COMMIT_MISMATCH")
        if key != "platform":
            actual = git(platform, "ls-tree", "HEAD", f"components/{key}").split()
            if len(actual) != 4 or actual[:3] != ["160000", "commit", specification["commit"]]:
                raise Refused("GITLINK_MISMATCH")
        for name, checksum in specification["files"].items():
            value = checked_bytes(root, name, checksum)
            destination = name if key == "platform" else f"components/{key}/{name}"
            if name.startswith("frontend/"):
                destination = "mateval-frontend/" + name.removeprefix("frontend/")
            else:
                destination = "platform-source/" + destination
            result[destination] = value
    return result


def crate_files(data: bytes, package: dict) -> dict[str, bytes]:
    if package["source"] != REGISTRY or digest(data) != package["checksum"]:
        raise Refused("CRATE_CHECKSUM_MISMATCH")
    prefix = f"{package['name']}-{package['version']}"
    result = {}
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        members = archive.getmembers()
        if len(members) > 20000 or sum(m.size for m in members) > 256 * 1024 * 1024:
            raise Refused("CRATE_LIMIT")
        for member in members:
            relative(member.name.rstrip("/"))
            if not (member.name == prefix or member.name.startswith(prefix + "/")):
                raise Refused("CRATE_MEMBER_REFUSED")
            if member.isdir():
                continue
            if not member.isfile() or not member.name.startswith(prefix + "/"):
                raise Refused("CRATE_MEMBER_REFUSED")
            name = member.name[len(prefix) + 1:]
            relative(name)
            if name in result or name == ".cargo-checksum.json":
                raise Refused("CRATE_MEMBER_REFUSED")
            stream = archive.extractfile(member)
            if stream is None:
                raise Refused("CRATE_MEMBER_REFUSED")
            result[name] = stream.read()
    checksum = {"package": package["checksum"], "files": {name: digest(value) for name, value in sorted(result.items())}}
    result[".cargo-checksum.json"] = (json.dumps(checksum, sort_keys=True, separators=(",", ":")) + "\n").encode()
    return result


def crate_archive(cache: Path, package: dict, download: bool) -> bytes:
    name = f"{package['name']}-{package['version']}.crate"
    try:
        data = regular_bytes(cache, name)
    except FileNotFoundError:
        if not download:
            raise Refused("PINNED_CRATE_MISSING") from None
        url = f"https://static.crates.io/crates/{package['name']}/{name}"
        with urllib.request.urlopen(url, timeout=30) as response:
            data = response.read(64 * 1024 * 1024 + 1)
        if len(data) > 64 * 1024 * 1024:
            raise Refused("CRATE_DOWNLOAD_LIMIT")
        if digest(data) != package["checksum"]:
            raise Refused("CRATE_CHECKSUM_MISMATCH")
        # Cache inputs remain read-only. Only the fresh materialization is written.
    if digest(data) != package["checksum"]:
        raise Refused("CRATE_CHECKSUM_MISMATCH")
    return data


def materialize(platform: Path, style: Path, elm_home: Path, cargo_cache: Path, destination: Path, download: bool):
    lock = json.loads((HERE / "sources.lock.json").read_text())
    elm_lock = json.loads((HERE / "elm-dependencies.lock.json").read_text())
    files = verify_sources(platform, lock)
    style_lock = json.loads(files["mateval-frontend/style-mrjam.json"])
    if style_lock["revision"] != "27111a95d0222c634e55fb2e3ff8e45041b40b16":
        raise Refused("STYLE_REVISION_MISMATCH")
    for name, checksum in style_lock["fichiers"].items():
        files["style-source/" + name] = checked_bytes(style, name, checksum)
    package_cache = elm_home / "0.19.1/packages"
    files["elm-home/0.19.1/packages/registry.dat"] = checked_bytes(package_cache, "registry.dat", elm_lock["registry_sha256"])
    expected_packages = {}
    manifest = json.loads(files["mateval-frontend/elm.json"])
    for section in ("dependencies", "test-dependencies"):
        for kind in ("direct", "indirect"):
            expected_packages.update(manifest[section][kind])
    if {name: value["version"] for name, value in elm_lock["packages"].items()} != expected_packages:
        raise Refused("ELM_DEPENDENCY_SET_MISMATCH")
    for name, package in elm_lock["packages"].items():
        directory = f"{name}/{package['version']}"
        for filename, checksum in package["files"].items():
            files[f"elm-home/0.19.1/packages/{directory}/{filename}"] = checked_bytes(package_cache / directory, filename, checksum)
    cargo = tomllib.loads(files["platform-source/Cargo.lock"].decode())
    registry_packages = [p for p in cargo["package"] if p.get("source")]
    if any(p["source"] != REGISTRY for p in registry_packages):
        raise Refused("UNAPPROVED_CARGO_SOURCE")
    if destination.exists() or destination.is_symlink():
        raise Refused("NEW_DESTINATION_REQUIRED")
    destination.mkdir(parents=True)
    for name, value in files.items():
        put(destination, name, value)
    for package in registry_packages:
        archive = crate_archive(cargo_cache, package, download)
        prefix = f"cargo-vendor/{package['name']}-{package['version']}"
        for name, value in crate_files(archive, package).items():
            put(destination, f"{prefix}/{name}", value)
    manifest = {
        "schema_version": 1,
        "scope": "Allowlisted build inputs only, no authority or deployment approval",
        "source_commits": {name: value["commit"] for name, value in lock["sources"].items()},
        "source_selection_sha256": digest((HERE / "sources.lock.json").read_bytes()),
        "elm_dependency_lock_sha256": digest((HERE / "elm-dependencies.lock.json").read_bytes()),
        "style_revision": style_lock["revision"],
        "source_files_sha256": {name: digest(value) for name, value in sorted(files.items())},
        "cargo_registry_packages": [{"name": p["name"], "version": p["version"], "sha256": p["checksum"]} for p in registry_packages],
        "cargo_vendor_checksum_files_sha256": {str(p.relative_to(destination)): digest(p.read_bytes()) for p in sorted((destination / "cargo-vendor").glob("*/.cargo-checksum.json"))},
        "deployment_authorized": False,
    }
    put(destination, "materialization.json", (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode())
    # The build can package the exact same manifest without referring outside src.
    put(destination / "platform-source", "materialization.json", (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode())
    return {"status": "prepared", "source_files": len(files), "cargo_packages": len(registry_packages), "elm_packages": len(elm_lock["packages"])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("platform", "style", "elm-home", "cargo-cache", "destination"):
        parser.add_argument("--" + flag, type=Path, required=True)
    parser.add_argument("--download-missing", action="store_true")
    args = parser.parse_args()
    try:
        result = materialize(args.platform, args.style, args.elm_home, args.cargo_cache, args.destination, args.download_missing)
    except Exception as error:
        code = str(error) if isinstance(error, Refused) else "BUILD_INPUT_PREPARATION_FAILED"
        print(json.dumps({"status": "refused", "code": code}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
