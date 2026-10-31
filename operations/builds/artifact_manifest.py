#!/usr/bin/env python3
"""Record output bytes and exact source refs, without treating a build as approval."""
import argparse
import hashlib
import json
import os
from pathlib import Path

from prepare import directory_descriptor, regular_bytes

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--inputs", type=Path, required=True)
parser.add_argument("--artifact", choices=("rust-server", "mateval-elm", "vision-journal-adoption"), required=True)
args = parser.parse_args()
output_directory = directory_descriptor(args.output)
if (args.output / "artifact.json").exists() or (args.output / "artifact.json").is_symlink():
    raise SystemExit("NEW_ARTIFACT_MANIFEST_REQUIRED")
source_bytes = regular_bytes(args.inputs, "materialization.json")
source = json.loads(source_bytes)
files = {}
for path in sorted(args.output.rglob("*")):
    if path.is_symlink():
        raise SystemExit("ARTIFACT_SYMLINK_REFUSED")
    if path.is_dir():
        continue
    name = path.relative_to(args.output).as_posix()
    files[name] = hashlib.sha256(regular_bytes(args.output, name)).hexdigest()
manifest = {
    "schema_version": 1,
    "artifact": args.artifact,
    "source_commits": source["source_commits"],
    "style_revision": source["style_revision"],
    "input_manifest_sha256": hashlib.sha256(source_bytes).hexdigest(),
    "toolchains_lock_sha256": hashlib.sha256((Path(__file__).parent / "toolchains.lock.json").read_bytes()).hexdigest(),
    "payload_sha256": files,
    "deployment_authorized": False,
    "runtime_qualification": "not_established_by_this_build",
}
manifest_descriptor = os.open("artifact.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o644, dir_fd=output_directory)
os.close(output_directory)
with os.fdopen(manifest_descriptor, "w") as destination:
    destination.write(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
