#!/usr/bin/env python3
"""Plan bounded Forgejo reconciliation from local, filtered JSON snapshots.

No token, API request or write is accepted. Logical field names must be mapped
and qualified against the observed Forgejo version before a future reconciler
may apply this proposal. Objects outside the managed scope remain untouched.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys

# Allow the reviewed sibling contract under Python -I -S, without PYTHONPATH or
# the caller's current directory taking part in module resolution.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from release_plan import COMMIT, HEX, Refusal, canonical, choice, digest, exact, integer, load, read_document, require, text

REPOSITORIES = {"mrjam-plateforme", "mrjam-validation", "vps-infrastructure"}
CONTROL_REPOSITORIES = {"mrjam-validation", "vps-infrastructure"}
PROTECTION_FIELDS = {"branch", "required_checks", "minimum_reviews", "force_push", "deletion", "administrator_bypass"}
REPOSITORY_FIELDS = {"private", "default_branch", "actions_enabled", "protection"}
RUNNER_FIELDS = {"enabled", "repository", "label", "ephemeral", "privileged", "docker_socket", "production_mounts", "production_network", "signing_credentials", "registration_secret_ref", "maximum_jobs", "qualification_profile"}


def validate_repository(value, desired=False):
    exact(value, REPOSITORY_FIELDS)
    for key in ("private", "actions_enabled"):
        require(type(value[key]) is bool)
    require(value["default_branch"] == "main")
    protection = exact(value["protection"], PROTECTION_FIELDS)
    require(protection["branch"] == "main")
    require(type(protection["required_checks"]) is list and len(protection["required_checks"]) <= 8)
    require(all(type(item) is str and re.fullmatch(r"[a-z][a-z0-9/-]{1,80}", item) for item in protection["required_checks"]))
    require(protection["required_checks"] == sorted(set(protection["required_checks"])))
    integer(protection["minimum_reviews"], 0, 4)
    for field in ("force_push", "deletion", "administrator_bypass"):
        require(type(protection[field]) is bool)
    if desired:
        require(value["private"] is True, "VISIBILITY_CHANGE_REFUSED")
        require(value["actions_enabled"] is False, "DEPLOYMENT_FREEZE")
        require(protection["required_checks"] == ["mrjam/independent-validation"], "REQUIRED_CHECKS_REFUSED")
        require(protection["minimum_reviews"] >= 1 and all(protection[field] is False for field in ("force_push", "deletion", "administrator_bypass")), "PROTECTION_WEAKENING_REFUSED")


def validate_runner(value, desired=False):
    exact(value, RUNNER_FIELDS)
    for field in ("enabled", "ephemeral", "privileged", "docker_socket", "production_network", "signing_credentials"):
        require(type(value[field]) is bool)
    choice(value["repository"], CONTROL_REPOSITORIES)
    require(value["label"] == "mrjam-synthetic-isolated")
    require(type(value["production_mounts"]) is list and value["production_mounts"] == [])
    require(value["registration_secret_ref"] == "ref:forgejo/runner-registration")
    require(value["qualification_profile"] == "synthetic-unqualified-for-vps")
    integer(value["maximum_jobs"], 1, 1)
    if desired:
        require(value["enabled"] is False, "DEPLOYMENT_FREEZE")
        require(value["ephemeral"] is True and all(value[field] is False for field in ("privileged", "docker_socket", "production_network", "signing_credentials")), "UNSAFE_RUNNER_REFUSED")


def validate_desired(value):
    exact(value, {"schema_version", "scope", "target", "deployment_freeze", "accepted_flow", "proposal_flow", "rules_revision", "controller_revision", "repositories", "runner"})
    require(type(value["schema_version"]) is int and value["schema_version"] == 1)
    require(value["scope"] == "prepared-not-adopted" and value["target"] == "forge.mrj.am")
    require(value["deployment_freeze"] is True, "DEPLOYMENT_FREEZE")
    require(value["accepted_flow"] == "forgejo-main-to-github-mirror", "COMPETING_AUTHORITY_REFUSED")
    require(value["proposal_flow"] == "github-proposal-to-forgejo-review", "PROPOSAL_FLOW_REFUSED")
    text(value["rules_revision"], COMMIT)
    text(value["controller_revision"], COMMIT)
    exact(value["repositories"], REPOSITORIES)
    for repository in value["repositories"].values():
        validate_repository(repository, desired=True)
    validate_runner(value["runner"], desired=True)
    return value


def validate_observed(value):
    exact(value, {"schema_version", "scope", "target", "authority", "revision", "repositories", "runner"})
    require(type(value["schema_version"]) is int and value["schema_version"] == 1)
    require(value["scope"] == "managed-settings-only" and value["target"] == "forge.mrj.am")
    require(value["authority"] == "unverified_observation")
    text(value["revision"], HEX)
    require(type(value["repositories"]) is dict and set(value["repositories"]).issubset(REPOSITORIES))
    for repository in value["repositories"].values():
        validate_repository(repository)
    if value["runner"] is not None:
        validate_runner(value["runner"])
    return value


def prepare(desired, observed, expected_observation_sha256):
    desired = validate_desired(desired)
    observed = validate_observed(observed)
    text(expected_observation_sha256, HEX)
    require(digest(canonical(observed)) == expected_observation_sha256, "OBSERVATION_CHANGED")
    changes = []
    for name in sorted(REPOSITORIES):
        wanted = desired["repositories"][name]
        current = observed["repositories"].get(name)
        if current is None:
            changes.append({"operation": "create_private_repository_with_frozen_actions", "repository": name, "desired": wanted})
            continue
        # A live/public repository cannot silently be adopted by this small plan.
        require(current["private"] is True, "PUBLIC_REPOSITORY_ADOPTION_REQUIRES_SEPARATE_REVIEW")
        for field in sorted(REPOSITORY_FIELDS):
            if current[field] != wanted[field]:
                changes.append({"operation": "set_managed_repository_field", "repository": name,
                                "field": field, "before": current[field], "after": wanted[field]})
    if observed["runner"] != desired["runner"]:
        changes.append({"operation": "prepare_disabled_isolated_runner_configuration", "desired": desired["runner"]})
    plan = {
        "schema_version": 1, "decision": "no-changes" if not changes else "review-plan-prepared",
        "production_authorized": False, "execution_supported": False,
        "desired_sha256": digest(canonical(desired)), "observation_sha256": expected_observation_sha256,
        "rules_revision": desired["rules_revision"], "controller_revision": desired["controller_revision"],
        "changes": changes, "unmanaged_objects": "untouched", "deletions": [],
        "blocking_gates": ["DEPLOYMENT_FREEZE", "FORGEJO_VERSION_AND_API_CAPABILITIES_UNKNOWN", "POLICY_NOT_INDEPENDENTLY_ADOPTED", "CONTROL_IDENTITIES_AND_ACLS_UNQUALIFIED", "OBSERVATION_NOT_AUTHENTICATED", "BOUNDED_API_APPLIER_NOT_IMPLEMENTED"],
    }
    return {**plan, "plan_sha256": digest(canonical(plan))}


def main():
    if len(sys.argv) != 4:
        print('{"decision":"reject","code":"INVALID_INVOCATION","production_authorized":false}')
        return 2
    try:
        result = prepare(load(read_document(sys.argv[1])), load(read_document(sys.argv[2])), sys.argv[3])
    except Refusal as error:
        print(json.dumps({"decision": "reject", "code": error.code, "production_authorized": False}, separators=(",", ":")))
        return 2
    except Exception:
        print('{"decision":"reject","code":"INVALID_INPUT","production_authorized":false}')
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
