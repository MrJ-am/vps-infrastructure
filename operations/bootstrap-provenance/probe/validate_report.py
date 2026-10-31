#!/usr/bin/env python3
"""Closed provenance filter; never imports the provenance collector."""
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import stat
import sys

sys.path.insert(0, str(Path(__file__).absolute().parent.parent))
import schema_core

SCHEMA_SHA256 = "a703c5024700435655a963595eb72187d0d3eba61bb5bdb9371913a3c3ef499a"


def schema():
    descriptor = os.open(Path(__file__).absolute().with_name("provenance.schema.json"),
                         os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError()
        raw = stream.read(8193)
    if len(raw) > 8192 or hashlib.sha256(raw).hexdigest() != SCHEMA_SHA256:
        raise ValueError()
    return schema_core.decode(raw)


def validate(raw):
    if len(raw) > 2048:
        raise ValueError()
    value = schema_core.decode(raw)
    rule = schema()
    if not schema_core._matches(value, rule, rule["$defs"]):
        raise ValueError()
    return value


def main():
    try:
        if len(sys.argv) != 1:
            raise ValueError()
        signal.signal(signal.SIGALRM, schema_core._deadline)
        signal.setitimer(signal.ITIMER_REAL, 5)
        schema_core._cap(resource.RLIMIT_CORE, 0)
        schema_core._cap(resource.RLIMIT_CPU, 2)
        schema_core._cap(resource.RLIMIT_AS, 128 * 1024 * 1024)
        schema_core._cap(resource.RLIMIT_NOFILE, 64)
        report = validate(sys.stdin.buffer.read(2049))
        print(json.dumps(report, separators=(",", ":"), sort_keys=True))
        return 0
    except Exception:
        return 65
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


if __name__ == "__main__":
    raise SystemExit(main())
