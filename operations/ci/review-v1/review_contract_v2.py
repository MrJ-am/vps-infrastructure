"""Review binding inside a future trusted Forgejo observer/signing service.

No CLI, network, credentials, merge, signature generation or deployment.
The caller must obtain complete projections directly from fixed Forgejo APIs.
Passing a dictionary here is not evidence that a human performed a review.
"""
import re

import contract as V
import signer as validation_signer

REPOSITORIES = frozenset(("Signature", "apprendre-a-demontrer", "etp-vie-affective",
                         "matheval", "mrjam-plateforme", "mrjam-validation",
                         "style-mrjam", "vision", "vps-infrastructure"))
REVIEW_STATES = frozenset(("APPROVED", "REQUEST_CHANGES", "REQUEST_REVIEW", "COMMENT", "PENDING"))


def identifier(value):
    V.integer(value, 1, 2**63 - 1)


def identifiers(values):
    V.require(type(values) is list and len(values) <= 10000, "IDENTITIES_REFUSED")
    for value in values: identifier(value)
    V.require(values == sorted(set(values)), "IDENTITIES_REFUSED")


def policy(value):
    V.exact(value, {"schema_version", "scope", "repository", "repository_id", "source_id",
                    "reviewer_ids", "technical_ids", "merge_actor_id", "validation_policy_sha256",
                    "target", "previous_generation", "not_before", "expires_at"})
    V.require(type(value["schema_version"]) is int and value["schema_version"] == 1)
    V.require(value["scope"] == "mrjam-forgejo-review-policy-v1")
    V.require(value["repository"] in REPOSITORIES and value["target"] == "srv1982677")
    identifier(value["repository_id"])
    identifier(value["merge_actor_id"])
    V.text(value["source_id"], re.compile(r"[a-z][a-z0-9-]{0,39}\Z"))
    identifiers(value["reviewer_ids"])
    identifiers(value["technical_ids"])
    V.require(value["reviewer_ids"] and value["merge_actor_id"] in value["technical_ids"]
              and not set(value["reviewer_ids"]) & set(value["technical_ids"]), "REVIEW_IDENTITY_REFUSED")
    V.text(value["validation_policy_sha256"], V.HEX)
    V.text(value["previous_generation"], V.STORE)
    for field in ("not_before", "expires_at"): V.integer(value[field], 0, 2**63 - 1)
    V.require(0 < value["expires_at"] - value["not_before"] <= 31 * 86400, "REVIEW_POLICY_WINDOW_REFUSED")


def approval_text(repository, number, head, manifest_sha256):
    """Exact text to display in the human review; no invisible JSON assertion."""
    V.require(repository in REPOSITORIES)
    identifier(number)
    V.text(head, V.REV)
    V.text(manifest_sha256, V.HEX)
    return ("J’approuve ce dossier de livraison.\n"
            "MRJAM-REVIEW-V1\n"
            "repository=MrJ-am/" + repository + "\n"
            "pull_request=" + str(number) + "\n"
            "head=" + head + "\n"
            "manifest_sha256=" + manifest_sha256)


def observation(value, *, now):
    V.exact(value, {"schema_version", "forgejo_version", "repository_id", "pull_request",
                    "author_id", "state", "draft", "merged", "base_ref", "base_sha",
                    "head_sha", "head_tree", "merge_base", "requested_reviewer_ids",
                    "reviews_complete", "reviews", "observed_at", "previous_generation"})
    V.require(type(value["schema_version"]) is int and value["schema_version"] == 1)
    V.require(value["forgejo_version"] == "17.0.1", "FORGEJO_VERSION_REFUSED")
    for key in ("repository_id", "pull_request", "author_id"): identifier(value[key])
    V.require(value["state"] == "open" and value["draft"] is False and value["merged"] is False,
              "PULL_REQUEST_STATE_REFUSED")
    V.require(value["base_ref"] == "main", "BASE_REF_REFUSED")
    for key in ("base_sha", "head_sha", "head_tree", "merge_base"): V.text(value[key], V.REV)
    V.require(value["base_sha"] == value["merge_base"] and value["base_sha"] != value["head_sha"],
              "FAST_FORWARD_REQUIRED")
    identifiers(value["requested_reviewer_ids"])
    V.require(not value["requested_reviewer_ids"], "REQUESTED_REVIEW_OUTSTANDING")
    V.require(value["reviews_complete"] is True, "INCOMPLETE_REVIEW_OBSERVATION")
    V.integer(value["observed_at"], max(0, now - 60), now)
    V.text(value["previous_generation"], V.STORE)
    rows = value["reviews"]
    V.require(type(rows) is list and 1 <= len(rows) <= 10000, "REVIEWS_REFUSED")
    seen = set()
    for row in rows:
        V.exact(row, {"id", "reviewer_id", "state", "body", "commit_id", "stale",
                      "official", "dismissed", "updated_at"})
        for key in ("id", "reviewer_id"): identifier(row[key])
        V.require(row["id"] not in seen, "DUPLICATE_REVIEW")
        seen.add(row["id"])
        V.require(row["state"] in REVIEW_STATES, "REVIEW_STATE_REFUSED")
        V.require(type(row["body"]) is str and len(row["body"].encode("utf-8")) <= 8192,
                  "REVIEW_BODY_LIMIT")
        V.text(row["commit_id"], V.REV)
        for key in ("stale", "official", "dismissed"): V.require(type(row[key]) is bool)
        V.integer(row["updated_at"], 0, value["observed_at"])


def bind_review(envelope, validation_policy, review_policy, observed, manifest,
                *, now, executable):
    """Return a checked unsigned payload, never an activation authorization.

    A separate service must collect the observation, verify branch protection,
    reobserve head/base, perform the bounded merge and sign its decision.
    This function cannot manufacture those facts or bypass that service.
    """
    V.integer(now, 0, 2**63 - 1)
    policy(review_policy)
    V.require(review_policy["not_before"] <= now < review_policy["expires_at"], "REVIEW_POLICY_EXPIRED")
    V.require(V.sha(V.canonical(validation_policy)) == review_policy["validation_policy_sha256"],
              "VALIDATION_POLICY_NOT_ADOPTED")
    validation_signer.verify(envelope, validation_policy, executable=executable, now=now)
    observation(observed, now=now)
    V.require(observed["repository_id"] == review_policy["repository_id"]
              and observed["previous_generation"] == review_policy["previous_generation"],
              "REVIEW_TARGET_REFUSED")
    sources = [source for source in envelope["payload"]["sources"]
               if source["id"] == review_policy["source_id"]]
    V.require(len(sources) == 1 and sources[0]["repository"] == "MrJ-am/" + review_policy["repository"]
              and sources[0]["revision"] == observed["head_sha"]
              and sources[0]["tree_sha"] == observed["head_tree"], "REVIEW_SOURCE_REFUSED")
    V.require(type(manifest) is bytes and 0 < len(manifest) <= 4 * 1024**2, "MANIFEST_LIMIT")
    manifest_sha = V.sha(manifest)
    text = approval_text(review_policy["repository"], observed["pull_request"], observed["head_sha"], manifest_sha)
    latest = {}
    active = {}
    for row in sorted(observed["reviews"], key=lambda row: row["id"]):
        if row["state"] in ("APPROVED", "REQUEST_CHANGES", "REQUEST_REVIEW"):
            latest[row["reviewer_id"]] = row
            if not row["dismissed"]:
                active[row["reviewer_id"]] = row
    # Forgejo keeps the last non-dismissed decision active. A dismissed newer
    # approval must neither conceal a rejection nor resurrect an old approval.
    for row in active.values():
        V.require(row["state"] not in ("REQUEST_CHANGES", "REQUEST_REVIEW"),
                  "REVIEW_REQUEST_UNRESOLVED")
    eligible = [row for reviewer, row in latest.items()
                if reviewer in review_policy["reviewer_ids"] and reviewer != observed["author_id"]
                and row["state"] == "APPROVED" and row["official"] and not row["stale"]
                and not row["dismissed"] and row["commit_id"] == observed["head_sha"]
                and row["body"] == text]
    V.require(eligible, "HUMAN_MANIFEST_REVIEW_REQUIRED")
    chosen = min(eligible, key=lambda row: row["id"])
    return {"schema_version": 1, "scope": "mrjam-forgejo-review-binding-v1",
            "review_policy_sha256": V.sha(V.canonical(review_policy)),
            "validation_attestation_sha256": V.sha(V.canonical(envelope)),
            "manifest_sha256": manifest_sha, "repository_id": observed["repository_id"],
            "pull_request": observed["pull_request"], "head_sha": observed["head_sha"],
            "head_tree": observed["head_tree"], "expected_base_sha": observed["base_sha"],
            "review_id": chosen["id"], "reviewer_id": chosen["reviewer_id"],
            "review_updated_at": chosen["updated_at"], "observed_at": observed["observed_at"],
            "target": review_policy["target"], "previous_generation": review_policy["previous_generation"],
            "merge_actor_id": review_policy["merge_actor_id"],
            "expires_at": min(now + 3600, review_policy["expires_at"], validation_policy["expires_at"])}
