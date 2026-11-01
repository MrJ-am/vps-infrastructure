#!/usr/bin/env python3
"""Record public build contents only; no deployment authority is asserted."""
import hashlib
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
files = {}
for path in sorted(root.rglob("*")):
    if path.is_symlink() or not (path.is_file() or path.is_dir()):
        raise ValueError("ARTIFACT_SPECIAL_FILE")
    if path.is_file():
        files[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
with (root / "artifact.json").open("x") as output:
    json.dump({"schema_version": 1, "repository": "https://github.com/MrJ-am/etp-vie-affective",
               "revision": sys.argv[2], "materialization_sha256": sys.argv[3],
               "files_sha256": files, "crypto_format": 1,
               "production_qualification": False}, output, indent=2, sort_keys=True)
    output.write("\n")
