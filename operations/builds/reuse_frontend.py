#!/usr/bin/env python3
"""Prove source equivalence to an existing Elm artifact without rebuilding it."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from prepare import HERE, Refused, checked_bytes, digest
from select_sources import BOOTSTRAP_LOCK_SHA256, commit_id, git_bytes

PREVIOUS_QUALIFICATION_SHA256 = "3d96b41aa5f91adb16bf8f9792ca69cdef648ff92d65997606db451ea8f082dd"


def equivalent(component: Path, old_commit: str, current_commit: str, files: dict) -> dict:
    for revision in (old_commit, current_commit):
        commit_id(revision)
    if git_bytes(component, "rev-parse", "HEAD").decode().strip() != current_commit:
        raise Refused("SOURCE_CHECKOUT_COMMIT_MISMATCH")
    previous_tree = git_bytes(component, "rev-parse", old_commit + ":frontend").decode().strip()
    current_tree = git_bytes(component, "rev-parse", current_commit + ":frontend").decode().strip()
    if previous_tree != current_tree:
        raise Refused("FRONTEND_TREE_CHANGED")
    for name, checksum in files.items():
        if not name.startswith("frontend/"):
            raise Refused("FRONTEND_SELECTION_REFUSED")
        checked_bytes(component, name, checksum)
    return {"previous_component_commit": old_commit, "current_component_commit": current_commit, "frontend_tree": current_tree, "selected_files_verified": len(files), "frontend_build_commit_retained": old_commit}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--component", required=True, type=Path)
    parser.add_argument("--current-commit", required=True)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()
    try:
        lock = json.loads(checked_bytes(HERE, "sources.lock.json", BOOTSTRAP_LOCK_SHA256))
        previous = json.loads(checked_bytes(HERE, "qualification.json", PREVIOUS_QUALIFICATION_SHA256))
        source = lock["sources"]["mateval"]
        result = equivalent(args.component, source["commit"], args.current_commit, {k:v for k,v in source["files"].items() if k.startswith("frontend/")})
        artifact = previous["artifacts"]["elm"]
        if artifact["manifest"]["source_commits"]["mateval"] != source["commit"]:
            raise Refused("PREVIOUS_ARTIFACT_SOURCE_MISMATCH")
        receipt = {"schema_version": 1, "scope": "Reuse of an unchanged frontend; no new Elm compilation claimed", "source_equivalence": result,
                   "previous_qualification_sha256": PREVIOUS_QUALIFICATION_SHA256, "previous_source_lock_sha256": BOOTSTRAP_LOCK_SHA256,
                   "artifact": {key: artifact[key] for key in ("store_path", "drv_path", "nar_hash", "artifact_manifest_sha256")},
                   "artifact_store_integrity_checked_by_this_tool": False, "required_separate_check": "nix-store --verify-path on the retained output, followed by runtime compatibility tests with the new backend",
                   "deployment_authorized": False}
        with args.destination.open("x") as output:
            output.write(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
        print(json.dumps({"status": "source-equivalent", "receipt_sha256": digest(args.destination.read_bytes()), "new_elm_build": False}))
        return 0
    except Exception as error:
        print(json.dumps({"status": "refused", "code": str(error) if isinstance(error, Refused) else "FRONTEND_REUSE_CHECK_FAILED"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
