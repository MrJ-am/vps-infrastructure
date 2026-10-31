#!/usr/bin/env python3
"""Create a deterministic public-code handoff from exact commits and export.

No production credential, runtime file, private graphic resource or mutable
working-tree source is selected. The tar is not compressed twice: its only
large entry is already the qualified gzip export.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile

HERE = Path(__file__).resolve().parent
INFRA = HERE.parents[1]
ARCHIVE = "mrjam-observation-adoption-20261031.tar"
EXPORT = "mrjam-observe-adoption-v2.nix-export.gz"
EXPORT_SHA256 = "81f3d750ef24577494019e6823492fe83c57f385a6c90dcda570b959eb42b1f6"
EXPORT_BYTES = 136243703
MANIFEST_SHA256 = "04c0dc51cbe4ca88daac24a180ccb8c19ae71781a36e0de07581e686f5b9d7d8"


def git(repo, revision, path):
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("EXACT_COMMIT_REQUIRED")
    environment = dict(os.environ, GIT_NO_REPLACE_OBJECTS="1", GIT_CONFIG_NOSYSTEM="1",
                       GIT_CONFIG_GLOBAL="/dev/null", GIT_TERMINAL_PROMPT="0")
    return subprocess.check_output(["git", "-C", str(repo), "show", revision + ":" + path],
                                   env=environment, timeout=20)


def sha_file(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def build(infra_commit, review_repo, review_commit, export, destination):
    if destination.exists() or destination.is_symlink():
        raise ValueError("NEW_DESTINATION_REQUIRED")
    if export.is_symlink() or not export.is_file() or export.stat().st_size != EXPORT_BYTES or sha_file(export) != EXPORT_SHA256:
        raise ValueError("QUALIFIED_EXPORT_MISMATCH")
    selected = {}
    for name in ("EXECUTION-HUMAINE.org", "SPECTRE-RELAIS-OBSERVATION.txt", "verify_delivery.py",
                 "delivery-manifest-20261031.json", "qualification-delivery-20261031.json"):
        selected[name] = git(INFRA, infra_commit, "operations/bootstrap-observation/" + name)
    if hashlib.sha256(selected["delivery-manifest-20261031.json"]).hexdigest() != MANIFEST_SHA256:
        raise ValueError("QUALIFIED_MANIFEST_MISMATCH")
    for name in ("package.nix", "observe.py", "collect.py", "bounded.py", "README.org"):
        selected["sources/bootstrap/" + name] = git(INFRA, infra_commit, "operations/bootstrap-observation/" + name)
    for name in ("adoption_probe.py", "validate_report.py", "adoption.schema.json"):
        selected["sources/adoption-v2/" + name] = git(INFRA, infra_commit, "operations/probes/adoption-v2/" + name)
    selected["sources/flake.lock"] = git(INFRA, infra_commit, "flake.lock")
    for name in ("bootstrap-tcg-cold-pass-20261031.json", "bootstrap-tcg-cold-assertions-20261031.json",
                 "bootstrap-systemd.nix", "bootstrap-sandbox-canary.py", "bootstrap-reprise-20261031.org"):
        selected["review/" + name] = git(review_repo, review_commit, "operational-review/" + name)
    evidence = selected["review/bootstrap-tcg-cold-pass-20261031.json"]
    if hashlib.sha256(evidence).hexdigest() != "4f89ef0d01f5af7d93bdcc189f150bf8daf7ce99ff9eee821a9e2faa971ccac5":
        raise ValueError("QUALIFICATION_MISMATCH")
    selected["REMISE.json"] = (json.dumps({
        "schema_version": 1, "scope": "Human-only bounded observation, no application deployment",
        "source": {"repository": "MrJ-am/vps-infrastructure", "commit": infra_commit},
        "review": {"repository": "MrJ-am/mrjam-validation", "commit": review_commit},
        "export": {"file": EXPORT, "bytes": EXPORT_BYTES, "sha256": EXPORT_SHA256},
        "manifest_sha256": MANIFEST_SHA256, "production_activation": False,
        "nix_trust_policy_changes": False,
        "source_excerpt_note": "The selected source excerpts are review material; full reproduction uses the exact repository commits."
    }, indent=2, sort_keys=True) + "\n").encode()
    checksums = {name: hashlib.sha256(data).hexdigest() for name, data in selected.items()}
    checksums[EXPORT] = EXPORT_SHA256
    selected["SHA256SUMS"] = "".join(f"{checksums[name]}  {name}\n" for name in sorted(checksums)).encode()
    destination.mkdir(parents=True)
    archive = destination / ARCHIVE
    with tarfile.open(archive, "w", format=tarfile.USTAR_FORMAT) as output:
        for name in sorted([*selected, EXPORT]):
            entry = tarfile.TarInfo(name)
            entry.uid = entry.gid = entry.mtime = 0
            entry.mode = 0o644
            entry.uname = entry.gname = ""
            entry.size = EXPORT_BYTES if name == EXPORT else len(selected[name])
            with (export.open("rb") if name == EXPORT else io.BytesIO(selected[name])) as stream:
                output.addfile(entry, stream)
    # Read every produced entry; no extraction or execution is involved.
    with tarfile.open(archive, "r:") as produced:
        members = produced.getmembers()
        if {entry.name for entry in members} != set(selected) | {EXPORT} or len(members) != len(selected) + 1:
            raise ValueError("HANDOFF_FILE_SET_MISMATCH")
        for entry in members:
            if not entry.isfile() or entry.name.startswith("/") or ".." in Path(entry.name).parts:
                raise ValueError("HANDOFF_ENTRY_REFUSED")
            expected = hashlib.sha256(selected[entry.name]).hexdigest() if entry.name in selected else EXPORT_SHA256
            with produced.extractfile(entry) as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
                    raise ValueError("HANDOFF_CONTENT_MISMATCH")
    result = {"archive": ARCHIVE, "bytes": archive.stat().st_size, "sha256": sha_file(archive),
              "sha256sums_sha256": hashlib.sha256(selected["SHA256SUMS"]).hexdigest(),
              "files_verified": len(selected) + 1,
              "infra_commit": infra_commit, "review_commit": review_commit,
              "reproducible_tar_metadata": True, "source_selection_from_git_objects": True}
    (destination / "handoff.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    (destination / "SHA256SUMS").write_bytes(selected["SHA256SUMS"])
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--infra-commit", required=True)
    parser.add_argument("--review-repo", type=Path, required=True)
    parser.add_argument("--review-commit", required=True)
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.infra_commit, args.review_repo, args.review_commit, args.export, args.destination), sort_keys=True))
