#!/usr/bin/env python3
"""Fetch only exact locked public application resources into a new local folder.

Reserved identity resources remain outside Git and public preparation archives.
No historical script is executed and no branch head or production URL is read.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
import urllib.request

from prepare import Refused, checked_bytes, digest, put, relative


def package_files(archive: bytes, selected: dict[str, dict]) -> dict[str, bytes]:
    expected = next(iter(selected.values()))["provenance"]
    if digest(archive) != expected["archive_sha256"] or "sha512-" + base64.b64encode(hashlib.sha512(archive).digest()).decode() != expected["integrity"]:
        raise Refused("PUBLIC_PACKAGE_INTEGRITY_MISMATCH")
    values = {}
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as package:
        members = package.getmembers()
        if len(members) > 2000 or sum(member.size for member in members) > 32 * 1024 * 1024:
            raise Refused("PUBLIC_PACKAGE_LIMIT")
        for member in members:
            relative(member.name.rstrip("/"))
            if not member.name.startswith("package/") or not (member.isdir() or member.isfile()):
                raise Refused("PUBLIC_PACKAGE_MEMBER_REFUSED")
            if not member.name.startswith("package/dist/") or member.isdir():
                continue
            name = "katex-dist/" + member.name.removeprefix("package/dist/")
            if name not in selected or name in values or member.size > 8 * 1024 * 1024:
                raise Refused("PUBLIC_PACKAGE_FILE_SET_MISMATCH")
            source = package.extractfile(member)
            if source is None:
                raise Refused("PUBLIC_PACKAGE_MEMBER_REFUSED")
            value = source.read()
            if digest(value) != selected[name]["sha256"]:
                raise Refused("PUBLIC_PACKAGE_FILE_HASH_MISMATCH")
            values[name] = value
    if set(values) != set(selected):
        raise Refused("PUBLIC_PACKAGE_FILE_SET_MISMATCH")
    return values


def fetch(lock: Path, expected_lock: str, destination: Path) -> dict:
    manifest = json.loads(checked_bytes(lock.parent, lock.name, expected_lock))
    selected = {}
    for entry in manifest["files"]:
        name = entry["source_path"]
        relative(name)
        if name in selected and selected[name]["sha256"] != entry["sha256"]:
            raise Refused("RESOURCE_DUPLICATE_CONFLICT")
        selected[name] = entry
    if destination.exists() or destination.is_symlink():
        raise Refused("NEW_DESTINATION_REQUIRED")
    values = {}
    for name, entry in selected.items():
        provenance = entry["provenance"]
        if not name.startswith("signature/"):
            continue
        if provenance["repository"] != "MrJ-am/Signature" or provenance["revision"] != "17194087eec9162bb5372221c43e1de0501dfe6a":
            raise Refused("IDENTITY_SOURCE_PIN_REFUSED")
        oid = provenance["git_blob"]
        if len(oid) != 40 or any(c not in "0123456789abcdef" for c in oid):
            raise Refused("IDENTITY_BLOB_REFUSED")
        response = subprocess.run(["gh", "api", "repos/MrJ-am/Signature/git/blobs/" + oid], capture_output=True, check=True, timeout=60)
        encoded = json.loads(response.stdout)
        if encoded.get("encoding") != "base64" or encoded.get("size", 0) > 1024 * 1024:
            raise Refused("IDENTITY_BLOB_LIMIT")
        value = base64.b64decode(encoded["content"].replace("\n", ""), validate=True)
        if hashlib.sha1(b"blob " + str(len(value)).encode() + b"\0" + value).hexdigest() != oid or digest(value) != entry["sha256"]:
            raise Refused("IDENTITY_BLOB_MISMATCH")
        values[name] = value
    packages = {name: entry for name, entry in selected.items() if name.startswith("katex-dist/")}
    if packages:
        expected = next(iter(packages.values()))["provenance"]
        if expected["url"] != "https://registry.npmjs.org/katex/-/katex-0.18.7.tgz" or any(entry["provenance"] != expected for entry in packages.values()):
            raise Refused("PUBLIC_PACKAGE_SOURCE_REFUSED")
        with urllib.request.urlopen(expected["url"], timeout=60) as response:
            archive = response.read(16 * 1024 * 1024 + 1)
        if len(archive) > 16 * 1024 * 1024:
            raise Refused("PUBLIC_PACKAGE_DOWNLOAD_LIMIT")
        values.update(package_files(archive, packages))
    if set(values) != set(selected):
        raise Refused("RESOURCE_FILE_SET_MISMATCH")
    destination.mkdir(parents=True)
    for name, value in values.items():
        put(destination, name, value)
    return {"status": "prepared", "files": len(values), "source_lock_sha256": expected_lock, "production_access": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-lock", required=True, type=Path)
    parser.add_argument("--source-lock-sha256", required=True)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(fetch(args.source_lock, args.source_lock_sha256, args.destination)))
        return 0
    except Exception as error:
        print(json.dumps({"status": "refused", "code": str(error) if isinstance(error, Refused) else "PUBLIC_RESOURCE_PREPARATION_FAILED"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
