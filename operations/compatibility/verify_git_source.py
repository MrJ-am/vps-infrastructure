#!/usr/bin/env python3
"""Cloud-only verification of a public source tree, including symlink objects.

This neither invokes source code nor reads symlink targets. The expected tree
comes from the separately selected upstream commit, never from this directory.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat


def object_digest(kind, data):
    return hashlib.sha1(kind + b" " + str(len(data)).encode() + b"\0" + data).digest()


def verify(root, expected):
    if not re.fullmatch(r"[0-9a-f]{40}", expected) or root.is_symlink() or not root.is_dir():
        raise ValueError("SOURCE_SELECTION_REFUSED")
    counts = {"files": 0, "directories": 0, "symlinks": 0, "bytes": 0}

    def directory(path):
        entries = []
        for entry in path.iterdir():
            if sum(counts[name] for name in ("files", "directories", "symlinks")) >= 120000:
                raise ValueError("SOURCE_BUDGET_EXCEEDED")
            metadata = entry.lstat()
            name = os.fsencode(entry.name)
            if stat.S_ISLNK(metadata.st_mode):
                target = os.fsencode(os.readlink(entry))
                if len(target) > 16384:
                    raise ValueError("SOURCE_BUDGET_EXCEEDED")
                mode, digest, key = b"120000", object_digest(b"blob", target), name
                counts["symlinks"] += 1
            elif stat.S_ISDIR(metadata.st_mode):
                counts["directories"] += 1
                mode, digest, key = b"40000", directory(entry), name + b"/"
            elif stat.S_ISREG(metadata.st_mode):
                counts["bytes"] += metadata.st_size
                if counts["bytes"] > 1024 * 1024 * 1024:
                    raise ValueError("SOURCE_BUDGET_EXCEEDED")
                descriptor = os.open(entry, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                with os.fdopen(descriptor, "rb") as stream:
                    before = os.fstat(stream.fileno())
                    if (before.st_ino, before.st_dev, before.st_size, before.st_mode) != (
                            metadata.st_ino, metadata.st_dev, metadata.st_size, metadata.st_mode):
                        raise ValueError("SOURCE_CHANGED")
                    digestor = hashlib.sha1(b"blob " + str(before.st_size).encode() + b"\0")
                    for block in iter(lambda: stream.read(1024 * 1024), b""):
                        digestor.update(block)
                    after = os.fstat(stream.fileno())
                    if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                            after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                        raise ValueError("SOURCE_CHANGED")
                mode = b"100755" if before.st_mode & 0o111 else b"100644"
                digest, key = digestor.digest(), name
                counts["files"] += 1
            else:
                raise ValueError("SOURCE_TYPE_REFUSED")
            entries.append((key, mode + b" " + name + b"\0" + digest))
        return object_digest(b"tree", b"".join(data for _, data in sorted(entries)))

    actual = directory(root).hex()
    if actual != expected:
        raise ValueError("SOURCE_TREE_MISMATCH")
    return {"tree": actual, "matches_expected": True, **counts}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--expected-tree", required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.source, args.expected_tree), sort_keys=True))
