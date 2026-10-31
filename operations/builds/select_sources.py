#!/usr/bin/env python3
"""Propose a fresh build selection from exact local Git objects, not loose files.

Only reviewed source categories and the unchanged, previously locked Mateval
frontend are selected. This is code preparation, never an approval authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

from prepare import HERE, Refused, checked_bytes, digest, git, relative

REPOSITORIES = {"platform": "MrJ-am/mrjam-plateforme", "vision": "MrJ-am/vision", "mateval": "MrJ-am/matheval"}
BOOTSTRAP_LOCK_SHA256 = "f8cc5fbce40ecf2ff50e27c3dae848594143a41714ac3a9e4fa730606a4bbb87"


def commit_id(value: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise Refused("EXACT_SOURCE_COMMIT_REQUIRED")
    return value


def git_bytes(root: Path, *arguments: str) -> bytes:
    environment = {"PATH": os.environ["PATH"], "LANG": "C", "LC_ALL": "C", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_TERMINAL_PROMPT": "0", "GIT_NO_REPLACE_OBJECTS": "1"}
    return subprocess.check_output(["git", "-c", "core.hooksPath=/dev/null", "-C", str(root), *arguments], env=environment, stderr=subprocess.DEVNULL, timeout=20)


def entries(root: Path, commit: str) -> dict[str, tuple[str, str, str]]:
    result = {}
    for record in git_bytes(root, "ls-tree", "-r", "-z", "--full-tree", commit_id(commit)).split(b"\0"):
        if not record:
            continue
        metadata, name = record.split(b"\t", 1)
        mode, kind, object_id = metadata.decode("ascii").split()
        path = name.decode("utf-8")
        relative(path)
        if any(ord(c) < 32 for c in path) or path in result:
            raise Refused("SOURCE_TREE_PATH_REFUSED")
        result[path] = mode, kind, object_id
    return result


def selected_path(component: str, name: str, baseline: dict) -> bool:
    if name in {"Cargo.toml", "Cargo.lock", "rust-toolchain.toml"}:
        return True
    if component == "platform":
        if name in {".gitmodules", "tools/mateval-browser-synthetic/bank.json", "crates/server/contracts/audition-catalogue.json"}:
            return True
        return any(name.startswith(f"crates/{crate}/") for crate in ("server", "audition", "log")) and (
            name.endswith(".rs") or name.endswith(".sql") or name.endswith("/Cargo.toml"))
    if component == "vision":
        if name in {"docs/CONTRAT-SEANCE.md", "docs/outils.json", "docs/tutoriel.json", "scripts/roles.sql"}:
            return True
        return (name.startswith(("src/", "tests/")) and name.endswith((".rs", ".sql"))) or (
            name.startswith(("migrations/", "journal/")) and name.endswith(".sql"))
    if component == "mateval":
        if name.startswith("frontend/"):
            return name in baseline["sources"]["mateval"]["files"]
        return (name.startswith(("src/", "tests/")) and name.endswith(".rs")) or (
            name.startswith("migrations/") and name.endswith(".sql"))
    raise Refused("SOURCE_COMPONENT_REFUSED")


def blob(root: Path, object_id: str) -> bytes:
    size = int(git_bytes(root, "cat-file", "-s", object_id))
    if size > 64 * 1024 * 1024:
        raise Refused("SOURCE_SIZE_LIMIT")
    data = git_bytes(root, "cat-file", "blob", object_id)
    if len(data) != size or hashlib.sha1(b"blob " + str(size).encode() + b"\0" + data).hexdigest() != object_id:
        raise Refused("SOURCE_GIT_OBJECT_MISMATCH")
    return data


def propose(platform: Path, commit: str, baseline: dict) -> dict:
    commit_id(commit)
    roots = {"platform": platform, "vision": platform / "components/vision", "mateval": platform / "components/mateval"}
    platform_entries = entries(platform, commit)
    revisions = {"platform": commit}
    for key in ("vision", "mateval"):
        mode, kind, object_id = platform_entries.get(f"components/{key}", ("", "", ""))
        if mode != "160000" or kind != "commit":
            raise Refused("EXACT_GITLINK_REQUIRED")
        revisions[key] = commit_id(object_id)
    sources = {}
    for key, root in roots.items():
        revision = revisions[key]
        if git(root, "rev-parse", "HEAD") != revision:
            raise Refused("SOURCE_CHECKOUT_COMMIT_MISMATCH")
        tree = entries(root, revision)
        files = {}
        for name, (mode, kind, object_id) in sorted(tree.items()):
            if not selected_path(key, name, baseline):
                continue
            if kind != "blob" or mode not in ("100644", "100755"):
                raise Refused("SOURCE_GIT_FILE_TYPE_REFUSED")
            files[name] = digest(blob(root, object_id))
        if "Cargo.toml" not in files or not any(name.endswith(".rs") for name in files):
            raise Refused("SOURCE_COMPONENT_INCOMPLETE")
        if key == "mateval":
            previous = baseline["sources"][key]["commit"]
            if git_bytes(root, "rev-parse", commit_id(previous) + ":frontend") != git_bytes(root, "rev-parse", revision + ":frontend"):
                raise Refused("FRONTEND_CHANGED_REQUIRES_NEW_QUALIFICATION")
            old = {name: value for name, value in baseline["sources"][key]["files"].items() if name.startswith("frontend/")}
            current = {name: value for name, value in files.items() if name.startswith("frontend/")}
            if current != old:
                raise Refused("FRONTEND_CHANGED_REQUIRES_NEW_QUALIFICATION")
        sources[key] = {"repository": REPOSITORIES[key], "commit": revision, "tree": git_bytes(root, "rev-parse", revision + "^{tree}").decode().strip(), "files": files}
    return {"schema_version": 1, "status": "proposed-source-selection-not-validation-authority", "selection": "Exact Git blobs in reviewed Rust/schema categories; unchanged previously qualified Mateval frontend", "baseline_source_lock_sha256": BOOTSTRAP_LOCK_SHA256, "sources": sources}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", required=True, type=Path)
    parser.add_argument("--platform-commit", required=True)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()
    try:
        baseline = json.loads(checked_bytes(HERE, "sources.lock.json", BOOTSTRAP_LOCK_SHA256))
        proposal = propose(args.platform, args.platform_commit, baseline)
        # The historical source lock is never overwritten to obtain a green build.
        with args.destination.open("x") as output:
            output.write(json.dumps(proposal, sort_keys=True, indent=2) + "\n")
        print(json.dumps({"status": "proposed", "sha256": digest(args.destination.read_bytes()), "source_files": sum(len(s["files"]) for s in proposal["sources"].values()), "deployment_authorized": False}))
        return 0
    except Exception as error:
        print(json.dumps({"status": "refused", "code": str(error) if isinstance(error, Refused) else "SOURCE_SELECTION_FAILED"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
