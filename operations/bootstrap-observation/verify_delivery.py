#!/usr/bin/env python3
"""Verify public delivery bytes or fixed Nix path-info metadata; never install.

The expected manifest is pinned here and must sit alongside this script.
The tool does not execute Nix, SSH, a package or any production operation.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

MANIFEST = "delivery-manifest-20261031.json"
MANIFEST_SHA256 = "04c0dc51cbe4ca88daac24a180ccb8c19ae71781a36e0de07581e686f5b9d7d8"
EXPORT = "mrjam-observe-adoption-v2.nix-export.gz"


def require(condition):
    if not condition:
        raise ValueError("DELIVERY_REFUSED")


def unique(items):
    result = {}
    for key, value in items:
        require(key not in result)
        result[key] = value
    return result


def open_regular(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        require(stat.S_ISREG(os.fstat(descriptor).st_mode))
        return os.fdopen(descriptor, "rb")
    except BaseException:
        os.close(descriptor)
        raise


def read_bounded(path, maximum):
    with open_regular(path) as stream:
        data = stream.read(maximum + 1)
    require(len(data) <= maximum)
    return data


def expected_manifest():
    raw = read_bounded(Path(__file__).parent / MANIFEST, 65536)
    require(hashlib.sha256(raw).hexdigest() == MANIFEST_SHA256)
    return json.loads(raw, object_pairs_hook=unique)


def verify_export(path, expected):
    with open_regular(path) as stream:
        require(os.fstat(stream.fileno()).st_size == expected["bytes"])
        checksum = hashlib.file_digest(stream, "sha256").hexdigest()
        require(os.fstat(stream.fileno()).st_size == expected["bytes"])
    require(checksum == expected["sha256"])


def verify_store(info, expected):
    if isinstance(info, list):
        require(all(isinstance(entry, dict) and isinstance(entry.get("path"), str) for entry in info))
        paths = [entry["path"] for entry in info]
        require(len(paths) == len(set(paths)))
        info = {entry["path"]: entry for entry in info}
    require(isinstance(info, dict) and set(info) == set(expected))
    for path, value in expected.items():
        actual = info[path]
        require(isinstance(actual, dict))
        require(actual.get("narHash") == value["nar_hash"])
        require(type(actual.get("narSize")) is int and actual["narSize"] == value["nar_size"])
        references = actual.get("references")
        require(isinstance(references, list) and all(isinstance(ref, str) for ref in references))
        require(len(references) == len(set(references)))
        require(sorted(references) == value["references"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--transfer-directory", type=Path)
    action.add_argument("--store-info", type=Path)
    arguments = parser.parse_args()
    try:
        manifest = expected_manifest()
        if arguments.transfer_directory is not None:
            verify_export(arguments.transfer_directory / EXPORT, manifest["exports"][EXPORT])
            print("DELIVERY_VALID")
        else:
            info = json.loads(read_bounded(arguments.store_info, 512 * 1024), object_pairs_hook=unique)
            verify_store(info, manifest["closure"])
            print("STORE_METADATA_MATCH")
    except Exception:
        print("DELIVERY_REFUSED", file=sys.stderr)
        return 65
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
