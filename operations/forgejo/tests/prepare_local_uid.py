#!/usr/bin/env python3
"""Copy public fixture code only, inside the disposable offline Nix container."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

ROOT = Path('/workspace/shared/mrjam-declarative-nix')
SOURCE = Path(__file__).resolve().parents[1]
FILES = ('worker.py', 'tests/qualify_nix_worker.py', 'tests/run_isolated_uid.py')


def main():
    if os.getuid() != 0 or os.environ.get('MRJAM_SYNTHETIC_CONTAINER') != '1' \
            or set(os.listdir('/sys/class/net')) != {'lo'} or len(sys.argv) != 2 \
            or not re.fullmatch(r'qualifier-code-[0-9-]+', sys.argv[1]):
        raise RuntimeError('OFFLINE_LOCAL_FIXTURE_REQUIRED')
    output = ROOT / 'qualifier-uid-59990'
    if not output.exists():
        output.mkdir(mode=0o700)
        os.chown(output, 59990, 59990)
    metadata = output.lstat()
    if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != 59990 \
            or metadata.st_gid != 59990 or metadata.st_mode & 0o777 != 0o700:
        raise RuntimeError('LOCAL_OUTPUT_REFUSED')
    destination = ROOT / sys.argv[1]
    destination.mkdir(mode=0o700)  # Never replace a previous fixture.
    records = {}
    for name in FILES:
        source = SOURCE / name
        metadata = source.lstat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or metadata.st_size > 262144:
            raise RuntimeError('SOURCE_REFUSED')
        payload = source.read_bytes()
        target = destination / 'forgejo' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        target.chmod(0o444)
        records[name] = hashlib.sha256(payload).hexdigest()
    binary = ROOT / 'runtime-export-20261031-02/mrjam-server'
    payload = binary.read_bytes()
    if hashlib.sha256(payload).hexdigest() != '7d91514354a124ea2e1e72b3841d6d9870dd7e8db6e700f07a3e59612a20b30c':
        raise RuntimeError('DIAGNOSTIC_BINARY_CHANGED')
    (destination / 'diagnostic-server').write_bytes(payload)
    (destination / 'diagnostic-server').chmod(0o555)
    (destination / 'sources.json').write_text(json.dumps(records, sort_keys=True) + '\n')
    (destination / 'sources.json').chmod(0o444)
    for directory, _, _ in os.walk(destination, topdown=False):
        Path(directory).chmod(0o555)
    print(json.dumps({'decision': 'prepared-local-fixture', 'fixture': destination.name, 'sources': records}))


if __name__ == '__main__':
    main()
