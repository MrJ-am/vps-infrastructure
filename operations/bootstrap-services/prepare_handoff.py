#!/usr/bin/env python3
"""Deterministic public code-only handoff from exact Git objects; no VPS action."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile

INFRA = Path(__file__).resolve().parents[2]
PREFIX = "operations/bootstrap-services/"
ARCHIVE = "mrjam-observation-services-20261101.tar"
EXPORT = "mrjam-observe-services-v1.nix-export.gz"
PACKAGE = "/nix/store/5shgv9hb5l98mkhvrrvwhq461vy5fr93-mrjam-observe-services-v1"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def git(repo, revision, path):
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("EXACT_COMMIT_REQUIRED")
    environment = dict(os.environ, GIT_NO_REPLACE_OBJECTS="1", GIT_CONFIG_NOSYSTEM="1",
                       GIT_CONFIG_GLOBAL="/dev/null", GIT_TERMINAL_PROMPT="0")
    return subprocess.check_output(["git", "-C", str(repo), "show", revision + ":" + path],
                                   env=environment, timeout=20)


def build(infra_commit, review_repo, review_commit, export, destination):
    if destination.exists() or destination.is_symlink():
        raise ValueError("NEW_DESTINATION_REQUIRED")
    selected = {name: git(INFRA, infra_commit, PREFIX + name) for name in (
        "README.org", "EXECUTION-HUMAINE.org", "SPECTRE-RELAIS.txt", "verify_delivery.py",
        "delivery-manifest-services-20261101.json", "qualification-systemd-20261101.json")}
    manifest = json.loads(selected["delivery-manifest-services-20261101.json"])
    receipt_bytes = selected["qualification-systemd-20261101.json"]
    receipt = json.loads(receipt_bytes)
    if (manifest["package"] != PACKAGE or receipt["candidate_package"] != PACKAGE
            or manifest["qualification_sha256"] != digest(receipt_bytes)
            or manifest["package_nar_hash"] != receipt["candidate_nar_hash"]
            or receipt["overall_passed"] is not True or len(receipt["groups_passed"]) != 5
            or not all(value is True for value in manifest["local_checks"].values())):
        raise ValueError("QUALIFICATION_MISMATCH")
    if export.is_symlink() or not export.is_file():
        raise ValueError("EXPORT_TYPE_REFUSED")
    export_bytes = export.read_bytes()
    expected_export = manifest["exports"][EXPORT]
    if len(export_bytes) != expected_export["bytes"] or digest(export_bytes) != expected_export["sha256"]:
        raise ValueError("QUALIFIED_EXPORT_MISMATCH")
    selected[EXPORT] = export_bytes
    source_paths = ["AGENTS.md", "operations/AGENTS.md", "operations/mise-en-service/mandat.org",
                    *receipt["source_sha256"], PREFIX + "export_delta.py", PREFIX + "prepare_handoff.py",
                    PREFIX + "test_delivery.py"]
    for path in source_paths:
        selected["sources/" + path] = git(INFRA, infra_commit, path)
    for path, expected in receipt["source_sha256"].items():
        if digest(selected["sources/" + path]) != expected:
            raise ValueError("QUALIFIED_SOURCE_CHANGED")
    review_prefix = "operational-review/services-observation-20261101/"
    for name in ("REVUE.org", "qualification-systemd.json", "candidate-systemd-test.nix", "vm-result.json",
                 *receipt["log_sha256"]):
        selected["review/" + name] = git(review_repo, review_commit, review_prefix + name)
    if selected["review/qualification-systemd.json"] != receipt_bytes:
        raise ValueError("REVIEW_RECEIPT_DIFFERS")
    if selected["review/candidate-systemd-test.nix"] != selected["sources/" + PREFIX + "systemd-test.nix"]:
        raise ValueError("REVIEW_TEST_DIFFERS")
    for name, expected in receipt["log_sha256"].items():
        if digest(selected["review/" + name]) != expected:
            raise ValueError("REVIEW_LOG_DIFFERS")
    for name in ("contract.py", "validate_report.py"):
        selected["filter/" + name] = selected["sources/" + PREFIX + name]
    selected["REMISE.json"] = (json.dumps({
        "schema_version": 1, "scope": "Human-only bounded service/identity observation; no activation",
        "source": {"repository": "MrJ-am/vps-infrastructure", "commit": infra_commit},
        "review": {"repository": "MrJ-am/mrjam-validation", "commit": review_commit},
        "candidate_source_commit": receipt["candidate_commit"],
        "export": {"file": EXPORT, **expected_export}, "package": PACKAGE,
        "package_nar_hash": manifest["package_nar_hash"],
        "manifest_sha256": digest(selected["delivery-manifest-services-20261101.json"]),
        "base_manifest_sha256": manifest["base_manifest_sha256"],
        "original_dependencies_required": True, "production_activation": False,
        "protected_independent_approval": False, "nix_trust_policy_changes": False,
        "source_excerpt_note": "Review excerpt; full reproduction uses exact repository commits."
    }, indent=2, sort_keys=True) + "\n").encode()
    selected["SHA256SUMS"] = "".join(f"{digest(selected[name])}  {name}\n" for name in sorted(selected)).encode()
    destination.mkdir(parents=True)
    archive = destination / ARCHIVE
    with tarfile.open(archive, "w", format=tarfile.USTAR_FORMAT) as output:
        for name, data in sorted(selected.items()):
            entry = tarfile.TarInfo(name)
            entry.uid = entry.gid = entry.mtime = 0
            entry.mode = 0o644
            entry.uname = entry.gname = ""
            entry.size = len(data)
            output.addfile(entry, io.BytesIO(data))
    with tarfile.open(archive, "r:") as produced:
        members = produced.getmembers()
        if {entry.name for entry in members} != set(selected) or len(members) != len(selected):
            raise ValueError("HANDOFF_FILE_SET_MISMATCH")
        for entry in members:
            if (not entry.isfile() or entry.name.startswith("/") or ".." in Path(entry.name).parts
                    or entry.mode != 0o644 or entry.uid != 0 or entry.gid != 0 or entry.mtime != 0):
                raise ValueError("HANDOFF_ENTRY_REFUSED")
            with produced.extractfile(entry) as stream:
                if digest(stream.read()) != digest(selected[entry.name]):
                    raise ValueError("HANDOFF_CONTENT_MISMATCH")
    result = {"archive": ARCHIVE, "bytes": archive.stat().st_size, "sha256": digest(archive.read_bytes()),
              "sha256sums_sha256": digest(selected["SHA256SUMS"]), "files_verified": len(selected),
              "infra_commit": infra_commit, "review_commit": review_commit,
              "reproducible_tar_metadata": True, "source_selection_from_git_objects": True}
    (destination / "handoff.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--infra-commit", required=True)
    parser.add_argument("--review-repo", type=Path, required=True)
    parser.add_argument("--review-commit", required=True)
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.infra_commit, args.review_repo, args.review_commit,
                           args.export, args.destination), sort_keys=True))
