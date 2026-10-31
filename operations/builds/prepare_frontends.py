#!/usr/bin/env python3
"""Materialize an already reviewed frontend lock, without changing its selection."""
import argparse
import json
from pathlib import Path

from frontend_inputs import materialize
from prepare import Refused, checked_bytes, digest

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--source-lock", required=True, type=Path)
parser.add_argument("--source-lock-sha256", required=True)
parser.add_argument("--root", action="append", default=[], metavar="NAME=PATH")
parser.add_argument("--destination", required=True, type=Path)
args = parser.parse_args()
try:
    lock = json.loads(checked_bytes(args.source_lock.parent, args.source_lock.name, args.source_lock_sha256))
    roots = {}
    for argument in args.root:
        name, separator, path = argument.partition("=")
        if not separator or name in roots or not Path(path).is_absolute():
            raise Refused("SOURCE_ROOT_MAPPING_REFUSED")
        roots[name] = Path(path)
    if set(roots) != {specification["root"] for specification in lock["files"].values()}:
        raise Refused("SOURCE_ROOT_SET_MISMATCH")
    result = materialize(args.source_lock, roots, args.destination)
    result["materialization_sha256"] = digest((args.destination / "materialization.json").read_bytes())
    print(json.dumps(result))
except Exception as error:
    print(json.dumps({"status": "refused", "code": str(error) if isinstance(error, Refused) else "FRONTEND_PREPARATION_FAILED"}))
    raise SystemExit(1)
