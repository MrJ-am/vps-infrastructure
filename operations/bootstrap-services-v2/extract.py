#!/usr/bin/env python3
"""Verify a frozen public code-only archive before extraction; no network/exec."""
import hashlib
import io
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import tarfile

EXPECTED = "24e7e18db366343b82bd65652903cbf586d50d5db7105b10e69a7877c635efee"
EXPECTED_BYTES = 31856640
MEMBERS = 53
SUMS = "ff6d963902c6ac8e4a7ec293aec5a9833b61ed786226c168db29382047d78470"


def main():
    if len(sys.argv) != 3:
        raise ValueError("ARGUMENTS_REFUSED")
    archive, destination = map(Path, sys.argv[1:])
    if destination.exists() or destination.is_symlink():
        raise ValueError("NEW_DESTINATION_REQUIRED")
    descriptor = os.open(archive, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size != EXPECTED_BYTES:
            raise ValueError("ARCHIVE_TYPE_OR_SIZE_REFUSED")
        # All later checks and extraction use this same immutable byte snapshot.
        data = stream.read(EXPECTED_BYTES + 1)
    if len(data) != EXPECTED_BYTES or hashlib.sha256(data).hexdigest() != EXPECTED:
        raise ValueError("ARCHIVE_HASH_MISMATCH")
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as source:
        entries = source.getmembers()
        names = [entry.name for entry in entries]
        if len(entries) != MEMBERS or len(set(names)) != MEMBERS:
            raise ValueError("MEMBERS_REFUSED")
        for entry in entries:
            path = PurePosixPath(entry.name)
            if (not entry.isfile() or path.is_absolute() or ".." in path.parts
                    or str(path) != entry.name or entry.mode != 0o644
                    or entry.uid != 0 or entry.gid != 0 or entry.mtime != 0):
                raise ValueError("MEMBER_REFUSED")
        sums = source.extractfile("SHA256SUMS").read()
        if hashlib.sha256(sums).hexdigest() != SUMS:
            raise ValueError("SUMS_HASH_MISMATCH")
        expected = {}
        for line in sums.decode("ascii").splitlines():
            checksum, name = line.split("  ", 1)
            if name in expected:
                raise ValueError("DUPLICATE_SUM")
            expected[name] = checksum
        if set(expected) != set(names) - {"SHA256SUMS"}:
            raise ValueError("SUMS_MEMBERS_MISMATCH")
        for name, checksum in expected.items():
            with source.extractfile(name) as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != checksum:
                    raise ValueError("MEMBER_HASH_MISMATCH")
        destination.mkdir(mode=0o700)
        for entry in entries:
            target = destination / entry.name
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as output, source.extractfile(entry) as input_stream:
                while chunk := input_stream.read(1024 * 1024):
                    output.write(chunk)
    print("ARCHIVE_AND_53_FILES_VERIFIED")


if __name__ == "__main__":
    main()
