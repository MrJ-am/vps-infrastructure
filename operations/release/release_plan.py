#!/usr/bin/env python3
"""Closed, local release dossier verifier and plan generator. Never a deployer.

MANIFEST POLICY OBSERVED EVIDENCE ARTIFACT_ROOT are local inputs selected by the
reviewer/controller. A policy passed by a caller is not an authenticated policy.
All successful outputs keep production_authorized=false and have explicit gates.
No shell command, subprocess, network call, store import or mutation exists here.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import PurePosixPath
import re
import stat
import sys
import time

MAX_DOCUMENT = 131_072
MAX_ARTIFACT = 2 * 1024**3
MAX_TOTAL = 8 * 1024**3
HEX = re.compile(r"[0-9a-f]{64}\Z")
COMMIT = re.compile(r"[0-9a-f]{40}\Z")
STORE = re.compile(r"/nix/store/[0-9abcdfghijklmnpqrsvwxyz]{32}-[A-Za-z0-9+._?=-]{1,100}\Z")
SRI = re.compile(r"sha256-[A-Za-z0-9+/]{43}=\Z")
TARGETS = {"mrjam-vps", "synthetic-vps"}
SOURCES = {"application", "infrastructure", "validation", "vision", "mateval"}
FILES = {
    "server", "frontends", "source_bundle", "cargo_lock", "frontend_locks",
    "toolchain_lock", "nix_lock", "build_config", "runtime_config",
    "migration_plan", "rules_bundle", "generation_nar", "previous_generation_nar",
    "backup_rehearsal_receipt", "resources_receipt", "session_compatibility_receipt",
}
CHECKS = {
    "rust", "elm", "http", "postgres", "privacy", "admission", "migrations",
    "restore", "continuity", "isolation", "nixos", "forgejo", "closure",
}
SECRET_REFS = {"database", "identity", "signer", "runner_registration"}


class Refusal(Exception):
    def __init__(self, code):
        self.code = code


def require(condition, code="INVALID_INPUT"):
    if not condition:
        raise Refusal(code)


def exact(value, names):
    require(type(value) is dict and set(value) == set(names))
    return value


def integer(value, minimum=0, maximum=2**63 - 1):
    require(type(value) is int and minimum <= value <= maximum)


def text(value, regex):
    require(type(value) is str and regex.fullmatch(value) is not None)


def choice(value, permitted):
    require(type(value) is str and value in permitted)


def unique(pairs):
    output = {}
    for key, value in pairs:
        require(key not in output, "DUPLICATE_FIELD")
        output[key] = value
    return output


def no_number(_value):
    raise Refusal("INVALID_NUMBER")


def load(raw):
    require(0 < len(raw) <= MAX_DOCUMENT, "DOCUMENT_LIMIT")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                          parse_float=no_number, parse_constant=no_number)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise Refusal("INVALID_JSON") from error


def read_document(path):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as handle:
            info = os.fstat(handle.fileno())
            require(stat.S_ISREG(info.st_mode), "INPUT_UNAVAILABLE")
            require(info.st_size <= MAX_DOCUMENT, "DOCUMENT_LIMIT")
            return handle.read(MAX_DOCUMENT + 1)
    except OSError as error:
        raise Refusal("INPUT_UNAVAILABLE") from error


def digest(value):
    return hashlib.sha256(value).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()


def check_store(value):
    exact(value, {"derivation", "output", "nar_hash"})
    text(value["derivation"], STORE)
    require(value["derivation"].endswith(".drv"))
    text(value["output"], STORE)
    require(not value["output"].endswith(".drv"))
    text(value["nar_hash"], SRI)
    raw = base64.b64decode(value["nar_hash"][7:], validate=True)
    require(len(raw) == 32 and base64.b64encode(raw).decode() == value["nar_hash"][7:])


def artifact_entry(value):
    exact(value, {"path", "sha256", "bytes"})
    text(value["sha256"], HEX)
    integer(value["bytes"], 1, MAX_ARTIFACT)
    require(type(value["path"]) is str and 0 < len(value["path"]) <= 240)
    path = PurePosixPath(value["path"])
    require(not path.is_absolute() and all(part not in {".", "..", ""} for part in path.parts), "ARTIFACT_PATH_REFUSED")
    require(str(path) == value["path"] and "\\" not in value["path"] and "\0" not in value["path"], "ARTIFACT_PATH_REFUSED")


def hash_artifact(rootfd, entry):
    """Open every component with NOFOLLOW; never follow a candidate symlink."""
    descriptors = []
    try:
        parent = rootfd
        parts = PurePosixPath(entry["path"]).parts
        for part in parts[:-1]:
            parent = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            descriptors.append(parent)
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        with os.fdopen(fd, "rb") as handle:
            before = os.fstat(handle.fileno())
            require(stat.S_ISREG(before.st_mode), "ARTIFACT_TYPE_REFUSED")
            require(before.st_size == entry["bytes"], "ARTIFACT_SIZE_MISMATCH")
            hashed = hashlib.sha256()
            size = 0
            while chunk := handle.read(1024 * 1024):
                size += len(chunk)
                require(size <= entry["bytes"], "ARTIFACT_SIZE_MISMATCH")
                hashed.update(chunk)
            after = os.fstat(handle.fileno())
            require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                    == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns), "ARTIFACT_CHANGED")
            require(size == entry["bytes"] and hashed.hexdigest() == entry["sha256"], "ARTIFACT_DIGEST_MISMATCH")
    except OSError as error:
        raise Refusal("ARTIFACT_UNAVAILABLE") from error
    finally:
        for fd in reversed(descriptors):
            os.close(fd)


def validate_manifest(value):
    exact(value, {"schema_version", "target", "mode", "sources", "files", "nix",
                  "previous_nix", "rules_revision", "required_checks", "migration",
                  "secret_references", "window"})
    require(type(value["schema_version"]) is int and value["schema_version"] == 1)
    choice(value["target"], TARGETS)
    choice(value["mode"], {"initial", "ordinary"})
    exact(value["sources"], SOURCES)
    for source in value["sources"].values():
        exact(source, {"commit", "tree_sha256"})
        text(source["commit"], COMMIT)
        text(source["tree_sha256"], HEX)
    text(value["rules_revision"], COMMIT)
    require(value["rules_revision"] == value["sources"]["validation"]["commit"], "RULES_MISMATCH")
    require(type(value["required_checks"]) is list and value["required_checks"] == sorted(CHECKS), "CHECKS_MISMATCH")
    exact(value["files"], FILES)
    for entry in value["files"].values():
        artifact_entry(entry)
    require(len({entry["path"] for entry in value["files"].values()}) == len(FILES), "ARTIFACT_ALIAS_REFUSED")
    require(sum(entry["bytes"] for entry in value["files"].values()) <= MAX_TOTAL, "ARTIFACT_TOTAL_LIMIT")
    check_store(value["nix"])
    check_store(value["previous_nix"])
    for field, artifact in (("nix", "generation_nar"), ("previous_nix", "previous_generation_nar")):
        nar_hash = "sha256-" + base64.b64encode(bytes.fromhex(value["files"][artifact]["sha256"])).decode()
        require(value[field]["nar_hash"] == nar_hash, "NAR_DIGEST_MISMATCH")
    migration = exact(value["migration"], {"current_schema", "resulting_schema", "old_reads", "old_writes",
                        "new_reads", "new_writes", "preserves_new_writes", "data_restore"})
    integer(migration["current_schema"], 0, 99999)
    integer(migration["resulting_schema"], 0, 99999)
    require(migration["resulting_schema"] >= migration["current_schema"], "DESTRUCTIVE_MIGRATION_REFUSED")
    for field in ("old_reads", "old_writes", "new_reads", "new_writes"):
        versions = migration[field]
        require(type(versions) is list and 1 <= len(versions) <= 16)
        for version in versions:
            integer(version, 0, 99999)
        require(versions == sorted(set(versions)))
    require(migration["preserves_new_writes"] is True, "NEW_WRITES_NOT_PRESERVED")
    require(migration["data_restore"] == "separate-reconciled-recovery-required", "DATA_RESTORE_REFUSED")
    require(all(migration["resulting_schema"] in migration[field]
                for field in ("old_reads", "old_writes", "new_reads", "new_writes")), "ROLLBACK_SCHEMA_INCOMPATIBLE")
    if value["mode"] == "ordinary":
        require(all(migration["current_schema"] in migration[field]
                    for field in ("old_reads", "old_writes", "new_reads", "new_writes")), "COEXISTENCE_SCHEMA_INCOMPATIBLE")
    refs = exact(value["secret_references"], SECRET_REFS)
    for reference in refs.values():
        text(reference, re.compile(r"ref:[a-z][a-z0-9/-]{1,100}\Z"))
    window = exact(value["window"], {"maximum_seconds", "abandon_after_seconds", "return_reserve_seconds"})
    for amount in window.values():
        integer(amount, 1, 10800)
    require(window["maximum_seconds"] <= 10800 and window["abandon_after_seconds"] + window["return_reserve_seconds"] <= window["maximum_seconds"], "INVALID_WINDOW")
    return value


def validate_policy(value):
    exact(value, {"schema_version", "scope", "target", "manifest_sha256", "evidence_sha256",
                  "observed_sha256", "rules_revision", "not_before", "expires_at",
                  "approval_reference", "deployment_freeze"})
    require(type(value["schema_version"]) is int and value["schema_version"] == 1)
    require(value["scope"] == "local-review-proposal")
    choice(value["target"], TARGETS)
    for field in ("manifest_sha256", "evidence_sha256", "observed_sha256"):
        text(value[field], HEX)
    text(value["rules_revision"], COMMIT)
    integer(value["not_before"])
    integer(value["expires_at"])
    require(0 < value["expires_at"] - value["not_before"] <= 3600, "INVALID_WINDOW")
    if value["approval_reference"] is not None:
        text(value["approval_reference"], HEX)
    require(value["deployment_freeze"] is True, "FREEZE_POLICY_REFUSED")
    return value


def validate_observed(value):
    exact(value, {"schema_version", "target", "authority", "active_manifest_sha256",
                  "generation", "schema", "active_slot"})
    require(type(value["schema_version"]) is int and value["schema_version"] == 1)
    require(value["authority"] == "unverified_observation")
    choice(value["target"], TARGETS)
    choice(value["active_slot"], {"blue", "green"})
    text(value["active_manifest_sha256"], HEX)
    check_store(value["generation"])
    integer(value["schema"], 0, 99999)
    return value


def validate_evidence(value):
    exact(value, {"schema_version", "scope", "authority", "manifest_sha256", "rules_revision", "checks"})
    require(type(value["schema_version"]) is int and value["schema_version"] == 1)
    require(value["scope"] == "synthetic-qualification" and value["authority"] == "unsigned-local-evidence")
    text(value["manifest_sha256"], HEX)
    text(value["rules_revision"], COMMIT)
    exact(value["checks"], CHECKS)
    for check in value["checks"].values():
        exact(check, {"status", "receipt_sha256"})
        require(check["status"] == "passed", "QUALIFICATION_INCOMPLETE")
        text(check["receipt_sha256"], HEX)
    return value


def prepare(manifest, policy, observed, evidence, root, now=None):
    manifest = validate_manifest(manifest)
    policy = validate_policy(policy)
    observed = validate_observed(observed)
    evidence = validate_evidence(evidence)
    now = int(time.time()) if now is None else now
    integer(now)
    require(policy["not_before"] <= now < policy["expires_at"], "REVIEW_WINDOW_CLOSED")
    subject = digest(canonical(manifest))
    require(manifest["target"] == policy["target"] == observed["target"], "TARGET_MISMATCH")
    require(subject == policy["manifest_sha256"] == evidence["manifest_sha256"], "MANIFEST_MISMATCH")
    require(digest(canonical(evidence)) == policy["evidence_sha256"], "EVIDENCE_MISMATCH")
    require(digest(canonical(observed)) == policy["observed_sha256"], "OBSERVATION_CHANGED")
    require(manifest["rules_revision"] == policy["rules_revision"] == evidence["rules_revision"], "RULES_MISMATCH")
    already_current = observed["active_manifest_sha256"] == subject
    expected_generation = manifest["nix"] if already_current else manifest["previous_nix"]
    expected_schema = manifest["migration"]["resulting_schema"] if already_current else manifest["migration"]["current_schema"]
    require(observed["generation"] == expected_generation, "PREVIOUS_GENERATION_MISMATCH")
    require(observed["schema"] == expected_schema, "SCHEMA_CHANGED")
    try:
        rootfd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for entry in manifest["files"].values():
                hash_artifact(rootfd, entry)
        finally:
            os.close(rootfd)
    except OSError as error:
        raise Refusal("ARTIFACT_ROOT_UNAVAILABLE") from error
    actions = []
    if not already_current:
        actions = ["acquire_exclusive_target_lease", "recheck_observation_and_policy", "verify_qualified_closure_and_all_references", "import_same_qualified_artifacts"]
        if manifest["mode"] == "initial":
            actions += ["freeze_all_writers_and_workers", "drain_all_channels", "capture_consistent_backup_through_bounded_operator"]
        actions += ["apply_only_reviewed_compatible_migration_plan", "start_inactive_private_slot", "require_business_readiness_200", "verify_nginx_configuration", "reload_nginx_gracefully", "verify_synthetic_continuity_and_write_integrity", "drain_previous_slot_without_forced_termination", "retain_previous_artifacts_and_compatible_schema"]
    rollback = [] if already_current else ["recheck_current_state_and_data_compatibility", "start_previous_qualified_artifact", "require_business_readiness_200", "verify_nginx_configuration", "reload_nginx_gracefully", "verify_new_writes_preserved", "drain_replaced_slot"]
    gates = ["DEPLOYMENT_FREEZE", "POLICY_NOT_INDEPENDENTLY_ADOPTED", "EVIDENCE_NOT_AUTHENTICATED", "RECEIPT_CONTENT_AND_RESULT_UNVERIFIED", "OBSERVATION_NOT_AUTHENTICATED", "SOURCE_TREE_AND_COMMIT_RELATION_UNVERIFIED", "NIX_CLOSURE_IMPORT_AND_REFERENCES_UNVERIFIED", "SECRET_REFERENCE_RESOLUTION_UNVERIFIED", "BOUNDED_DEPLOYER_NOT_QUALIFIED"]
    gates.append("APPROVAL_MISSING" if policy["approval_reference"] is None else "APPROVAL_REFERENCE_NOT_AUTHENTICATED")
    plan = {
        "schema_version": 1, "decision": "no-changes" if already_current else "review-plan-prepared",
        "production_authorized": False, "execution_supported": False,
        "manifest_sha256": subject, "policy_sha256": digest(canonical(policy)),
        "observation_sha256": digest(canonical(observed)), "evidence_sha256": digest(canonical(evidence)),
        "target": manifest["target"], "new_generation": manifest["nix"],
        "previous_manifest_sha256": observed["active_manifest_sha256"],
        "previous_generation": manifest["previous_nix"], "inactive_slot": "green" if observed["active_slot"] == "blue" else "blue",
        "artifact_sha256": {name: entry["sha256"] for name, entry in manifest["files"].items()},
        "actions": actions, "rollback_actions": rollback,
        "data_restore": "separate-reconciled-recovery-required", "window": manifest["window"],
        "blocking_gates": gates,
    }
    return {**plan, "plan_sha256": digest(canonical(plan))}


def main():
    if len(sys.argv) != 6:
        print('{"decision":"reject","code":"INVALID_INVOCATION","production_authorized":false}')
        return 2
    try:
        values = [load(read_document(path)) for path in sys.argv[1:5]]
        result = prepare(*values, sys.argv[5])
    except Refusal as error:
        result = {"decision": "reject", "code": error.code, "production_authorized": False}
        print(json.dumps(result, separators=(",", ":")))
        return 2
    except Exception:
        print('{"decision":"reject","code":"INVALID_INPUT","production_authorized":false}')
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
