#!/usr/bin/env python3
"""Local public archive verifier/extractor only. No network or execution."""
import hashlib
from pathlib import Path, PurePosixPath
import sys
import tarfile

EXPECTED = "5837158667d13cdfe791d58f5d0e54909196f490a53dee72c41a0c83d501ff5e"
# Pin copied from the producer receipt; never replace it to force success.
SUMS = "12e1a4ddeb49a8fa490053df50ed3d6b6b3d30e83363b5621dc27dc845cd22f0"

def main():
    if len(sys.argv) != 3:
        raise ValueError("ARGUMENTS_REFUSED")
    archive, destination = map(Path, sys.argv[1:])
    if archive.is_symlink() or not archive.is_file() or destination.exists() or destination.is_symlink():
        raise ValueError("PATH_REFUSED")
    with archive.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != EXPECTED:
            raise ValueError("ARCHIVE_HASH_MISMATCH")
    with tarfile.open(archive, "r:") as source:
        entries = source.getmembers()
        names = [entry.name for entry in entries]
        if len(entries) != 33 or len(set(names)) != 33:
            raise ValueError("MEMBERS_REFUSED")
        for entry in entries:
            parts = PurePosixPath(entry.name)
            if (not entry.isfile() or parts.is_absolute() or ".." in parts.parts
                    or str(parts) != entry.name or entry.mode != 0o644):
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
    print("ARCHIVE_AND_33_FILES_VERIFIED")

if __name__ == "__main__":
    main()
