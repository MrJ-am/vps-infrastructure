#!/usr/bin/env python3
"""Reassemble the fixed public observation archive; never import or run it."""
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
NAME = 'mrjam-observation-adoption-20261031.tar'
EXPECTED = '0615970d94bf91bc3308bede2d21c6a9eb7150ba420816f936baa9c021f514aa'
SIZE = 136396800


def require(ok):
    if not ok:
        raise ValueError('ARCHIVE_REFUSED')


def check_existing(path):
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_size == SIZE)
    with path.open('rb') as stream:
        require(hashlib.file_digest(stream, 'sha256').hexdigest() == EXPECTED)


def assemble():
    require(len(sys.argv) == 1)
    target = ROOT/NAME
    if target.exists() or target.is_symlink():
        check_existing(target)
        return
    manifest = json.loads((ROOT/'publication.json').read_bytes())
    require(manifest['schema_version'] == 1 and manifest['archive'] == NAME and
            manifest['bytes'] == SIZE and manifest['sha256'] == EXPECTED)
    parts = manifest['parts']
    require(len(parts) == 3 and [p['file'] for p in parts] ==
            [NAME + '.part-%02d' % i for i in range(1, 4)])
    fd, temporary = tempfile.mkstemp(prefix='.mrjam-assembly-', dir=ROOT)
    try:
        total, combined = 0, hashlib.sha256()
        with os.fdopen(fd, 'wb') as output:
            for part in parts:
                count, digest = 0, hashlib.sha256()
                descriptor = os.open(ROOT/part['file'], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                with os.fdopen(descriptor, 'rb') as source:
                    info = os.fstat(source.fileno())
                    require(stat.S_ISREG(info.st_mode) and info.st_size == part['bytes'])
                    while raw := source.read(1024*1024):
                        count += len(raw)
                        total += len(raw)
                        require(count <= part['bytes'] and total <= SIZE)
                        digest.update(raw)
                        combined.update(raw)
                        output.write(raw)
                require(count == part['bytes'] and digest.hexdigest() == part['sha256'])
            require(total == SIZE and combined.hexdigest() == EXPECTED)
            output.flush()
            os.fsync(output.fileno())
        # Publish without ever overwriting an existing file.
        os.link(temporary, target)
    finally:
        os.unlink(temporary)


if __name__ == '__main__':
    try:
        assemble()
    except Exception:
        print('ARCHIVE_REFUSED', file=sys.stderr)
        raise SystemExit(2)
    print('ARCHIVE_VERIFIED ' + EXPECTED + '  ' + NAME)
