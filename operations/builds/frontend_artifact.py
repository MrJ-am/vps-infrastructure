#!/usr/bin/env python3
"""Record exact public assets, preserving application and style revisions."""
import argparse
import json
import os
from pathlib import Path

from prepare import digest, directory_descriptor, put, regular_bytes

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--inputs", type=Path, required=True)
parser.add_argument("--frontend", choices=("vision", "log", "audition"), required=True)
args = parser.parse_args()
descriptor = directory_descriptor(args.output)
os.close(descriptor)
source_bytes = regular_bytes(args.inputs, "materialization.json")
source = json.loads(source_bytes)
metadata = source["frontends"][args.frontend]
files = {}
for path in sorted(args.output.rglob("*")):
    if path.is_symlink():
        raise SystemExit("ARTIFACT_SYMLINK_REFUSED")
    if path.is_dir():
        continue
    name = path.relative_to(args.output).as_posix()
    files[name] = digest(regular_bytes(args.output, name))
if "artifact.json" in files:
    raise SystemExit("NEW_ARTIFACT_MANIFEST_REQUIRED")
manifest = {
    "schema_version": 1,
    "artifact": args.frontend + "-elm",
    "source_commits": {args.frontend: metadata["source_commit"], "style": metadata["style_revision"], "signature": metadata["signature_revision"]},
    "style_revision": metadata["style_revision"],
    "input_manifest_sha256": digest(source_bytes),
    "toolchains_lock_sha256": digest(regular_bytes(Path(__file__).parent, "toolchains.lock.json")),
    "payload_sha256": files,
    "deployment_authorized": False,
    "runtime_qualification": "not_established_by_this_build",
}
put(args.output, "artifact.json", (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode())
