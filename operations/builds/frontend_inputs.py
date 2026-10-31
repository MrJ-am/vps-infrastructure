#!/usr/bin/env python3
"""Export three pinned public frontends and verify their closed build inputs.

The generated lock is a review proposal. It does not grant deployment authority.
No repository fetch, package installation or application code runs here.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from prepare import HERE, Refused, checked_bytes, digest, git, put, regular_bytes, relative
from select_sources import blob, commit_id, entries

STYLE = {
    "vision": "27111a95d0222c634e55fb2e3ff8e45041b40b16",
    "log": "a998822b21352c98f6ad90738f3123711c49834b",
    "audition": "cebba1824b6b5e939ae0155481ed87d7a98771e0",
}
PUBLIC_EXTENSIONS = {".css", ".js", ".mjs", ".json", ".svg", ".png", ".jpg", ".jpeg", ".webp", ".ico", ".woff", ".woff2", ".ttf", ".otf", ".txt", ".md"}


def application_path(frontend: str, name: str) -> bool:
    base = "interface/" if frontend == "vision" else f"interface-{frontend}/"
    if frontend == "vision" and name in {"docs/openapi.json", "docs/mobile-live-test-openapi.json"}:
        return True
    if not name.startswith(base):
        return False
    local = name.removeprefix(base)
    if local.startswith(("src/", "tests/")):
        return local.endswith((".elm", ".py"))
    if frontend == "vision":
        return local in {"elm.json", "package.json", "style.lock.json", "compiler.py", "app.html", "pont.js", "exports.js"} or (
            local.startswith(("identite/", "visuels/")) and Path(local).suffix in PUBLIC_EXTENSIONS)
    return local in {"elm.json", "index.html", "pont.js"}


def select_application(root: Path, revision: str, frontend: str) -> dict:
    if git(root, "rev-parse", "HEAD") != commit_id(revision):
        raise Refused("FRONTEND_CHECKOUT_COMMIT_MISMATCH")
    result = {}
    for name, (mode, kind, oid) in sorted(entries(root, revision).items()):
        if not application_path(frontend, name):
            continue
        if kind != "blob" or mode not in ("100644", "100755"):
            raise Refused("FRONTEND_SOURCE_TYPE_REFUSED")
        data = blob(root, oid)
        # The worktree is an input only when it matches the selected Git object.
        checked_bytes(root, name, digest(data))
        result[name] = {"sha256": digest(data), "git_blob": oid}
    if not result:
        raise Refused("FRONTEND_SOURCE_EMPTY")
    return result


def verify_tree(root: Path, lock: dict) -> dict:
    """Verify every selected byte and refuse additions, links or special files."""
    expected = lock["files"]
    for name, specification in expected.items():
        checked_bytes(root, name, specification["sha256"])
    actual = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise Refused("FRONTEND_SYMLINK_REFUSED")
        if path.is_file():
            actual.add(path.relative_to(root).as_posix())
        elif not path.is_dir():
            raise Refused("FRONTEND_FILE_TYPE_REFUSED")
    if actual != set(expected) | {"materialization.json"}:
        raise Refused("FRONTEND_FILE_SET_MISMATCH")
    manifest = json.loads(regular_bytes(root, "materialization.json"))
    if manifest["source_files_sha256"] != {name: s["sha256"] for name, s in expected.items()}:
        raise Refused("FRONTEND_MANIFEST_FILE_MISMATCH")
    if manifest["frontends"] != lock["frontends"] or manifest["deployment_authorized"] is not False:
        raise Refused("FRONTEND_MANIFEST_METADATA_MISMATCH")
    return {"status": "verified", "source_files": len(expected), "frontends": sorted(lock["frontends"])}


def verify(root: Path, source_lock: Path, expected_manifest: str) -> dict:
    manifest = json.loads(checked_bytes(root, "materialization.json", expected_manifest))
    lock_bytes = regular_bytes(source_lock.parent, source_lock.name)
    if manifest["source_selection_sha256"] != digest(lock_bytes):
        raise Refused("FRONTEND_SOURCE_LOCK_MISMATCH")
    return verify_tree(root, json.loads(lock_bytes))


def materialize(source_lock: Path, roots: dict[str, Path], destination: Path) -> dict:
    lock_bytes = regular_bytes(source_lock.parent, source_lock.name)
    lock = json.loads(lock_bytes)
    # Read and verify all files before creating an incomplete output directory.
    values = {name: checked_bytes(roots[s["root"]], s["path"], s["sha256"]) for name, s in lock["files"].items()}
    if destination.exists() or destination.is_symlink():
        raise Refused("NEW_DESTINATION_REQUIRED")
    destination.mkdir(parents=True)
    for name, data in values.items():
        put(destination, name, data)
    manifest = {"schema_version": 1, "source_selection_sha256": digest(lock_bytes), "frontends": lock["frontends"],
                "source_files_sha256": {name: digest(data) for name, data in values.items()}, "deployment_authorized": False}
    put(destination, "materialization.json", (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode())
    return verify_tree(destination, lock)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-lock", required=True, type=Path)
    parser.add_argument("--inputs", required=True, type=Path)
    parser.add_argument("--manifest-sha256", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.inputs, args.source_lock, args.manifest_sha256)))
        return 0
    except Exception as error:
        print(json.dumps({"status": "refused", "code": str(error) if isinstance(error, Refused) else "FRONTEND_INPUTS_INVALID"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
