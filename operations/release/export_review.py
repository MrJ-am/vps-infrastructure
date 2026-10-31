#!/usr/bin/env python3
"""Cloud-only export of selected public artifacts; no activation or SQL runner.

The selection and evidence are read from read-only repository mounts. Nix
integrity checks are content checks, not signatures or production approval.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
from urllib.parse import quote


SELECTION = Path(__file__).with_name("review-artifacts-20261031.json")
SELECTION_SHA256 = "17944c0c802082f9650493c1da8122357a15fc676d2e7fe68ebe17d5fd20f580"
ROOTS = {name: Path("/workspace") / name for name in ("vps-infrastructure", "mrjam-validation")}
OUTPUT_PARENT = Path("/workspace/shared/mrjam-declarative-nix")
STORE_PATH = re.compile(r"/nix/store/[0-9a-df-np-sv-z]{32}-[A-Za-z0-9+._?=-]+")
NAR_HASH = re.compile(r"sha256-[A-Za-z0-9+/]{43}=")


class Refused(ValueError):
    pass


def require(ok: bool, code: str) -> None:
    if not ok:
        raise Refused(code)


def checksum(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def public_bytes(path: Path) -> bytes:
    # Ancestors are immutable read-only bind mounts for the duration of export.
    require(path.is_absolute() and path.resolve() == path, "AMBIGUOUS_PUBLIC_PATH")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_size <= 2 * 1024 * 1024, "PUBLIC_FILE_REFUSED")
        data = stream.read(2 * 1024 * 1024 + 1)
        after = os.fstat(stream.fileno())
        require(len(data) == before.st_size and
                (before.st_ino, before.st_mtime_ns, before.st_ctime_ns) ==
                (after.st_ino, after.st_mtime_ns, after.st_ctime_ns), "PUBLIC_FILE_CHANGED")
        return data


def unique(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        require(key not in result, "DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def load_selection(path: Path, expected: str, roots: dict[str, Path]) -> tuple[dict, dict[str, bytes]]:
    data = public_bytes(path)
    require(hashlib.sha256(data).hexdigest() == expected, "SELECTION_HASH_MISMATCH")
    selection = json.loads(data, object_pairs_hook=unique)
    require(set(selection) == {"schema_version", "scope", "production_authorized", "roots",
                              "evidence_sha256", "limits", "not_included", "notes"}, "SELECTION_FIELDS")
    require(selection["schema_version"] == 1 and selection["scope"] == "public-review-only"
            and selection["production_authorized"] is False, "REVIEW_SCOPE_REQUIRED")
    selected = selection["roots"]
    require(isinstance(selected, dict) and 1 <= len(selected) <= 32, "ROOT_COUNT")
    require(all(STORE_PATH.fullmatch(p) and NAR_HASH.fullmatch(h) for p, h in selected.items()), "ROOT_FORMAT")
    limits = selection["limits"]
    require(limits == {"max_closure_paths": 64, "max_total_nar_bytes": 268435456}, "REVIEW_LIMITS")
    evidence = selection["evidence_sha256"]
    require(isinstance(evidence, dict) and 1 <= len(evidence) <= 32, "EVIDENCE_COUNT")
    contents = {"selection.json": data}
    for name, expected_hash in evidence.items():
        pieces = name.split("/")
        require(len(pieces) >= 2 and pieces[0] in roots and
                all(re.fullmatch(r"[A-Za-z0-9_.-]+", p) and p not in (".", "..") for p in pieces),
                "EVIDENCE_PATH_REFUSED")
        payload = public_bytes(roots[pieces[0]].joinpath(*pieces[1:]))
        require(hashlib.sha256(payload).hexdigest() == expected_hash, "EVIDENCE_HASH_MISMATCH")
        contents["evidence/" + name] = payload
    return selection, contents


def run(*args: str) -> bytes:
    return subprocess.check_output(args, timeout=240)


def path_info(roots: dict, store: str | None = None) -> dict:
    args = ["nix", "path-info", "--offline", "--json", "--recursive"]
    if store is not None:
        args.extend(["--store", store])
    raw = json.loads(run(*args, *sorted(roots)))
    entries = raw if isinstance(raw, dict) else {e["path"]: e for e in raw}
    return {p: {"nar_hash": e["narHash"], "nar_size": e["narSize"],
                "references": sorted(e["references"])} for p, e in sorted(entries.items())}


def validate_closure(selection: dict, closure: dict) -> None:
    limits = selection["limits"]
    require(0 < len(closure) <= limits["max_closure_paths"], "CLOSURE_COUNT")
    for path, info in closure.items():
        require(STORE_PATH.fullmatch(path) is not None and NAR_HASH.fullmatch(info["nar_hash"]) is not None,
                "CLOSURE_FORMAT")
        require(type(info["nar_size"]) is int and info["nar_size"] > 0, "CLOSURE_SIZE")
        require(not (set(info["references"]) - set(closure)), "INCOMPLETE_CLOSURE")
    require(sum(e["nar_size"] for e in closure.values()) <= limits["max_total_nar_bytes"], "CLOSURE_BUDGET")
    for path, expected in selection["roots"].items():
        require(path in closure and closure[path]["nar_hash"] == expected, "ROOT_NAR_MISMATCH")


def produce(destination: Path) -> dict:
    require(os.environ.get("MRJAM_SYNTHETIC_CONTAINER") == "1", "CLOUD_FIXTURE_REQUIRED")
    require(all(os.statvfs(p).f_flag & os.ST_RDONLY for p in ROOTS.values()), "READ_ONLY_SOURCES_REQUIRED")
    require(destination.parent == OUTPUT_PARENT and re.fullmatch(r"review-export-[a-z0-9-]+", destination.name)
            is not None and destination.parent.resolve() == OUTPUT_PARENT, "LOCAL_NEW_DESTINATION_REQUIRED")
    require(not destination.exists() and not destination.is_symlink(), "NEW_DESTINATION_REQUIRED")
    selection, evidence = load_selection(SELECTION, SELECTION_SHA256, ROOTS)
    closure = path_info(selection["roots"])
    validate_closure(selection, closure)
    run("nix", "store", "verify", "--offline", "--no-trust", "--recursive", *sorted(selection["roots"]))
    destination.mkdir(mode=0o755)
    export_path = destination / "public-artifacts.nix-export"
    with export_path.open("xb") as output:
        subprocess.run(["nix-store", "--export", *sorted(closure)], stdout=output, check=True, timeout=240)
    require(export_path.stat().st_size <= 269484032, "EXPORT_BUDGET")
    compressed = destination / (export_path.name + ".gz")
    with export_path.open("rb") as source, compressed.open("xb") as output:
        with gzip.GzipFile(filename="", fileobj=output, mode="wb", mtime=0) as stream:
            shutil.copyfileobj(source, stream)
    with tempfile.TemporaryDirectory(prefix="mrjam-review-import-") as scratch:
        store = "local?root=" + quote(scratch, safe="/")
        with export_path.open("rb") as source:
            result = subprocess.run(["nix-store", "--store", store, "--import"], stdin=source,
                                    stdout=subprocess.PIPE, check=True, timeout=240)
        require(set(result.stdout.decode().splitlines()) == set(closure), "IMPORTED_PATH_SET_MISMATCH")
        imported = path_info(selection["roots"], store)
        require(imported == closure, "IMPORTED_CLOSURE_MISMATCH")
        run("nix", "store", "verify", "--offline", "--no-trust", "--recursive", "--store", store,
            *sorted(selection["roots"]))
    # Recheck every selected input before publishing a successful manifest.
    require(load_selection(SELECTION, SELECTION_SHA256, ROOTS)[1] == evidence, "EVIDENCE_CHANGED")
    for name, contents in evidence.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(contents)
    manifest = {
        "schema_version": 1, "authority": "unverified-local-export-result",
        "scope": "public-review-only", "selection_sha256": SELECTION_SHA256,
        "closure": closure, "closure_paths": len(closure), "selected_roots": len(selection["roots"]),
        "total_nar_bytes": sum(e["nar_size"] for e in closure.values()),
        "exports": {p.name: {"bytes": p.stat().st_size, "sha256": checksum(p)} for p in (export_path, compressed)},
        "checks": {"recursive_integrity": True, "fresh_store_import": True,
                   "same_paths_nar_hashes_sizes_references": True, "evidence_before_after_unchanged": True},
        "nix_version": run("nix", "--version").decode().strip(), "fresh_import_uid": os.geteuid(),
        "nix_trust_settings_modified": False, "imported_program_executed": False,
        "production_access": False, "production_ready": False, "production_authorized": False,
        "limits": selection["not_included"],
    }
    with (destination / "review-manifest.json").open("x") as stream:
        stream.write(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    files = sorted(p for p in destination.rglob("*") if p.is_file())
    with (destination / "SHA256SUMS").open("x") as stream:
        stream.writelines(f"{checksum(p)}  {p.relative_to(destination)}\n" for p in files)
    return {"decision": "exported-and-import-checked", "closure_paths": len(closure),
            "selected_roots": len(selection["roots"]), "exports": manifest["exports"],
            "manifest_sha256": checksum(destination / "review-manifest.json")}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(produce(args.destination), sort_keys=True))
