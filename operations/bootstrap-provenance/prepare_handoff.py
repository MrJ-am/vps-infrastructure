#!/usr/bin/env python3
"""Assemble a deterministic, code-only provenance handoff from exact Git commits.

No production operation, credential, working-tree source or implicit download.
The small delta requires the unchanged original runtime closure on the target.
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
PREFIX = "operations/bootstrap-provenance/"
ARCHIVE = "mrjam-observation-provenance-20261031.tar"
EXPORT = "mrjam-observe-provenance-v1.nix-export.gz"
PACKAGE = "/nix/store/jg09160604wr7nv4z00f02vn48ssxayh-mrjam-observe-provenance-v1"


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
    selected = {}
    for name in ("EXECUTION-HUMAINE.org", "SPECTRE-RELAIS.txt", "verify_delivery.py",
                 "delivery-manifest-provenance-20261031.json", "qualification-systemd-20261031.json",
                 "qualification-delivery-20261031.json"):
        selected[name] = git(INFRA, infra_commit, PREFIX + name)
    manifest = json.loads(selected["delivery-manifest-provenance-20261031.json"])
    receipt_bytes = selected["qualification-systemd-20261031.json"]
    receipt = json.loads(receipt_bytes)
    if (manifest["package"] != PACKAGE or receipt["candidate_package"] != PACKAGE
            or manifest["qualification_sha256"] != digest(receipt_bytes)
            or manifest["package_nar_hash"] != receipt["candidate_nar_hash"]
            or receipt["overall_passed"] is not True or len(receipt["groups_passed"]) != 8
            or not all(value is True for value in manifest["local_checks"].values())):
        raise ValueError("QUALIFICATION_MISMATCH")
    if export.is_symlink() or not export.is_file():
        raise ValueError("EXPORT_TYPE_REFUSED")
    export_bytes = export.read_bytes()
    expected_export = manifest["exports"][EXPORT]
    if len(export_bytes) != expected_export["bytes"] or digest(export_bytes) != expected_export["sha256"]:
        raise ValueError("QUALIFIED_EXPORT_MISMATCH")
    selected[EXPORT] = export_bytes
    source_paths = ["flake.lock", "AGENTS.md", "operations/AGENTS.md", "operations/mise-en-service/mandat.org",
                    "operations/bootstrap-observation/bounded.py", "operations/probes/adoption-v2/adoption_probe.py",
                    "operations/probes/adoption-v2/validate_report.py"]
    source_paths += [PREFIX + name for name in (
        "package.nix", "observe.py", "collect.py", "probe/provenance_probe.py",
        "probe/validate_report.py", "probe/provenance.schema.json", "tests/test_provenance.py",
        "tests/test_delivery.py", "README.org", "export_delta.py", "prepare_handoff.py")]
    for path in source_paths:
        selected["sources/" + path] = git(INFRA, infra_commit, path)
    for name in ("provenance-systemd.nix", "provenance-systemd-pass-20261031.json",
                 "provenance-systemd-assertions-20261031.json", "provenance-revue-20261031.org"):
        selected["review/" + name] = git(review_repo, review_commit, "operational-review/" + name)
    for name in ("native.log", "systemd-pass.log", "systemd-interrupted.log"):
        selected["review/logs/" + name] = git(review_repo, review_commit,
                                            "operational-review/provenance-logs-20261031/" + name)
    if selected["review/provenance-systemd-pass-20261031.json"] != receipt_bytes:
        raise ValueError("REVIEW_RECEIPT_DIFFERS")
    for source, expected in receipt["source_sha256"].items():
        if source.startswith("/workspace/vps-infrastructure/"):
            data = selected["sources/" + source.removeprefix("/workspace/vps-infrastructure/")]
        elif source == "/workspace/mrjam-validation/operational-review/provenance-systemd.nix":
            data = selected["review/provenance-systemd.nix"]
        else:
            raise ValueError("UNEXPECTED_QUALIFIED_SOURCE")
        if digest(data) != expected:
            raise ValueError("QUALIFIED_SOURCE_CHANGED")
    selected["filter/probe/validate_report.py"] = selected["sources/" + PREFIX + "probe/validate_report.py"]
    selected["filter/probe/provenance.schema.json"] = selected["sources/" + PREFIX + "probe/provenance.schema.json"]
    selected["filter/schema_core.py"] = selected["sources/operations/probes/adoption-v2/validate_report.py"]
    selected["REMISE.json"] = (json.dumps({
        "schema_version": 1, "scope": "Human-only bounded provenance observation; delta, no activation",
        "source": {"repository": "MrJ-am/vps-infrastructure", "commit": infra_commit},
        "review": {"repository": "MrJ-am/mrjam-validation", "commit": review_commit},
        "candidate_source_commit": receipt["candidate_commit"], "contract_commit": receipt["contract_commit"],
        "export": {"file": EXPORT, **expected_export}, "package": PACKAGE,
        "package_nar_hash": manifest["package_nar_hash"],
        "manifest_sha256": digest(selected["delivery-manifest-provenance-20261031.json"]),
        "base_manifest_sha256": manifest["base_manifest_sha256"],
        "original_dependencies_required": True, "production_activation": False,
        "protected_independent_approval": False, "nix_trust_policy_changes": False,
        "source_excerpt_note": "Selected review material; full reproduction uses the exact repository commits."
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
    print(json.dumps(build(args.infra_commit, args.review_repo, args.review_commit,
                           args.export, args.destination), sort_keys=True))
