#!/usr/bin/env python3
"""Export exact frontend Nix outputs locally, never publish reserved resources."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

from prepare import Refused, digest, put, regular_bytes


def command(*arguments: str) -> bytes:
    return subprocess.check_output(arguments, timeout=60)


def file_metadata(path: Path) -> dict:
    with path.open("rb") as source:
        checksum = hashlib.file_digest(source, "sha256").hexdigest()
    return {"sha256": checksum, "bytes": path.stat().st_size}


def export(build_result: Path, mateval_reuse: Path, destination: Path) -> dict:
    selected = json.loads(regular_bytes(build_result.parent, build_result.name))
    reused = json.loads(regular_bytes(mateval_reuse.parent, mateval_reuse.name))
    paths = {}
    for build in selected:
        path = build["outputs"]["out"]
        match = re.fullmatch(r"/nix/store/[0-9a-z]{32}-mrjam-(vision|log|audition)-elm-[0-9a-f]{12}", path)
        if not match or match[1] in paths:
            raise Refused("FRONTEND_OUTPUT_SELECTION_REFUSED")
        paths[match[1]] = path
    if set(paths) != {"vision", "log", "audition"}:
        raise Refused("FRONTEND_OUTPUT_SET_MISMATCH")
    paths["mateval"] = reused["artifact"]["store_path"]
    if not re.fullmatch(r"/nix/store/[0-9a-z]{32}-mrjam-mateval-elm-preparation-[0-9a-f]{12}", paths["mateval"]):
        raise Refused("REUSED_FRONTEND_OUTPUT_REFUSED")
    if destination.exists() or destination.is_symlink():
        raise Refused("NEW_DESTINATION_REQUIRED")
    info_bytes = command("nix", "path-info", "--json", "--recursive", *paths.values())
    raw_info = json.loads(info_bytes)
    info = raw_info if isinstance(raw_info, dict) else {entry["path"]: entry for entry in raw_info}
    artifacts = {}
    for name, path in paths.items():
        command("nix-store", "--verify-path", path)
        artifact_bytes = regular_bytes(Path(path), "artifact.json")
        artifact = json.loads(artifact_bytes)
        if artifact["artifact"] != name + "-elm":
            raise Refused("FRONTEND_ARTIFACT_KIND_MISMATCH")
        if name == "mateval" and (digest(artifact_bytes) != reused["artifact"]["artifact_manifest_sha256"] or info[path]["narHash"] != reused["artifact"]["nar_hash"]):
            raise Refused("REUSED_FRONTEND_CHANGED")
        if info[path]["references"]:
            raise Refused("UNEXPECTED_STATIC_RUNTIME_REFERENCE")
        total = 0
        for filename, expected in artifact["payload_sha256"].items():
            if not filename.startswith(f"share/mrjam/{name}/"):
                raise Refused("FRONTEND_PAYLOAD_PREFIX_MISMATCH")
            value = regular_bytes(Path(path), filename, 16 * 1024 * 1024)
            if digest(value) != expected:
                raise Refused("FRONTEND_PAYLOAD_HASH_MISMATCH")
            total += len(value)
        actual = set()
        for file in Path(path).rglob("*"):
            if file.is_symlink():
                raise Refused("FRONTEND_OUTPUT_SYMLINK")
            if file.is_file():
                actual.add(file.relative_to(path).as_posix())
            elif not file.is_dir():
                raise Refused("FRONTEND_OUTPUT_FILE_TYPE")
        if actual != set(artifact["payload_sha256"]) | {"artifact.json"}:
            raise Refused("FRONTEND_OUTPUT_FILE_SET_MISMATCH")
        artifacts[name] = {"store_path": path, "nar_hash": info[path]["narHash"], "nar_size": info[path]["narSize"],
                           "artifact_manifest_sha256": digest(artifact_bytes), "payload_bytes": total,
                           "payload_files": len(artifact["payload_sha256"]), "payload_prefix": f"share/mrjam/{name}/",
                           "mount": "/matheval/" if name == "mateval" else "/", "artifact": artifact}
    destination.mkdir(parents=True)
    put(destination, "path-info.json", info_bytes)
    for name, path in paths.items():
        shutil.copytree(path, destination / "runtime" / name)
    closure = command("nix-store", "--query", "--requisites", *paths.values()).decode().splitlines()
    if set(closure) != set(paths.values()):
        raise Refused("UNEXPECTED_FRONTEND_CLOSURE")
    export_path = destination / "mrjam-frontends-private-delivery.nix-export"
    with export_path.open("xb") as output:
        subprocess.run(["nix-store", "--export", *sorted(closure)], stdout=output, check=True, timeout=60)
    compressed = destination / (export_path.name + ".gz")
    with export_path.open("rb") as source, compressed.open("xb") as output, gzip.GzipFile(filename="", mode="wb", fileobj=output, mtime=0) as stream:
        shutil.copyfileobj(source, stream)
    record = {"schema_version": 1, "scope": "Local exact artifacts for existing application integration; reserved identity resources; no public preparation archive",
              "artifacts": artifacts, "closure_paths": sorted(closure), "nix_version": command("nix", "--version").decode().strip(),
              "exports": {file.name: file_metadata(file) for file in (export_path, compressed)},
              "production_access": False, "deployment_authorized": False}
    put(destination, "export-metadata.json", (json.dumps(record, sort_keys=True, indent=2) + "\n").encode())
    return {"status": "exported_locally", "artifacts": len(artifacts), "payload_bytes": sum(a["payload_bytes"] for a in artifacts.values())}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-result", required=True, type=Path)
    parser.add_argument("--mateval-reuse", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(export(args.build_result, args.mateval_reuse, args.destination)))
    except Exception as error:
        print(json.dumps({"status": "refused", "code": str(error) if isinstance(error, Refused) else "FRONTEND_EXPORT_FAILED"}))
        raise SystemExit(1)
