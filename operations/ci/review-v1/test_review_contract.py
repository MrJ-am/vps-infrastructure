"""Invented review projections and real validation signatures; no Forgejo API."""
import copy
from pathlib import Path
import sys
import time
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "authority-v1"))
import test_authority as fixtures
import contract as V
import signer
sys.path.insert(0, str(HERE))
import review_contract as R


class Tests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.AuthorityTests("runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        f = self.fixture
        f.policy["sources"][0]["repository"] = "MrJ-am/mrjam-plateforme"
        f.report["sources"] = copy.deepcopy(f.policy["sources"])
        raw = V.canonical(f.report)
        f.receipt["artifacts"][-1] = {"name": "verification.json", "bytes": len(raw), "sha256": V.sha(raw)}
        self.now = int(time.time())
        self.envelope = signer.attest(f.receipt, f.report, f.proposal, f.policy, f.key,
                                      now=self.now, executable=fixtures.OPENSSL)
        self.manifest = b'{"synthetic_manifest":"not deployable"}\n'
        self.policy = {
            "schema_version": 1, "scope": "mrjam-forgejo-review-policy-v1",
            "repository": "mrjam-plateforme", "repository_id": 11, "source_id": "synthetic",
            "reviewer_ids": [101], "technical_ids": [201, 202, 203], "merge_actor_id": 201,
            "validation_policy_sha256": V.sha(V.canonical(f.policy)), "target": "srv1982677",
            "previous_generation": "/nix/store/" + "0" * 32 + "-synthetic-generation",
            "not_before": self.now - 60, "expires_at": self.now + 60,
        }
        self.observed = {
            "schema_version": 1, "forgejo_version": "17.0.1", "repository_id": 11,
            "pull_request": 12, "author_id": 202, "state": "open", "draft": False,
            "merged": False, "base_ref": "main", "base_sha": "1" * 40,
            "head_sha": "e" * 40, "head_tree": "f" * 40, "merge_base": "1" * 40,
            "requested_reviewer_ids": [], "reviews_complete": True,
            "observed_at": self.now, "previous_generation": self.policy["previous_generation"],
            "reviews": [{"id": 1, "reviewer_id": 101, "state": "APPROVED",
                         "body": R.approval_text("mrjam-plateforme", 12, "e" * 40, V.sha(self.manifest)),
                         "commit_id": "e" * 40, "stale": False, "official": True,
                         "dismissed": False, "updated_at": self.now - 1}],
        }

    def bind(self, **changes):
        values = dict(envelope=self.envelope, validation_policy=self.fixture.policy,
                      review_policy=self.policy, observed=self.observed, manifest=self.manifest,
                      now=self.now, executable=fixtures.OPENSSL)
        values.update(changes)
        return R.bind_review(**values)

    def test_real_signature_and_exact_human_manifest_binding(self):
        value = self.bind()
        self.assertEqual(value["manifest_sha256"], V.sha(self.manifest))
        self.assertEqual(value["validation_attestation_sha256"], V.sha(V.canonical(self.envelope)))
        self.assertEqual(value["reviewer_id"], 101)
        self.assertNotIn("production_authorized", value)
        self.assertNotIn("signature", value)

    def test_changed_head_tree_base_target_or_stale_observation_refused(self):
        for key, value in (("head_sha", "2" * 40), ("head_tree", "2" * 40),
                           ("base_sha", "2" * 40), ("base_ref", "other"),
                           ("repository_id", 99), ("observed_at", self.now - 61),
                           ("previous_generation", "/nix/store/" + "1" * 32 + "-other")):
            with self.subTest(key=key), self.assertRaises(V.Refused):
                self.bind(observed={**self.observed, key: value})

    def test_self_review_stale_dismissed_unofficial_or_different_commit_refused(self):
        for key, value in (("stale", True), ("dismissed", True), ("official", False),
                           ("commit_id", "2" * 40), ("reviewer_id", 202), ("state", "COMMENT")):
            observed = copy.deepcopy(self.observed)
            observed["reviews"][0][key] = value
            with self.subTest(key=key), self.assertRaises(V.Refused): self.bind(observed=observed)
        with self.assertRaises(V.Refused): self.bind(observed={**self.observed, "author_id": 101})

    def test_approve_on_head_without_manifest_body_is_insufficient(self):
        observed = copy.deepcopy(self.observed)
        observed["reviews"][0]["body"] = "Looks good"
        with self.assertRaisesRegex(V.Refused, "HUMAN_MANIFEST"): self.bind(observed=observed)
        with self.assertRaisesRegex(V.Refused, "HUMAN_MANIFEST"): self.bind(manifest=self.manifest + b" ")

    def test_later_comment_does_not_replace_approval_but_dismissed_latest_does(self):
        observed = copy.deepcopy(self.observed)
        row = {**observed["reviews"][0], "id": 2, "updated_at": self.now, "state": "COMMENT", "body": "comment"}
        observed["reviews"].append(row)
        self.assertEqual(self.bind(observed=observed)["review_id"], 1)
        row.update(state="APPROVED", dismissed=True)
        with self.assertRaises(V.Refused): self.bind(observed=observed)

    def test_changes_requested_block_until_newer_approval(self):
        observed = copy.deepcopy(self.observed)
        row = {**observed["reviews"][0], "id": 2, "updated_at": self.now, "state": "REQUEST_CHANGES"}
        observed["reviews"].append(row)
        with self.assertRaisesRegex(V.Refused, "UNRESOLVED"): self.bind(observed=observed)
        observed["reviews"].append({**observed["reviews"][0], "id": 3, "updated_at": self.now})
        self.assertEqual(self.bind(observed=observed)["review_id"], 3)

    def test_incomplete_duplicates_or_requested_review_refused(self):
        for value in ({**self.observed, "reviews_complete": False},
                      {**self.observed, "requested_reviewer_ids": [101]},
                      {**self.observed, "reviews": self.observed["reviews"] * 2}):
            with self.assertRaises(V.Refused): self.bind(observed=value)

    def test_forged_signature_or_substituted_validation_policy_refused(self):
        envelope = copy.deepcopy(self.envelope)
        envelope["signature"] = "A" * 86 + "=="
        with self.assertRaises(V.Refused): self.bind(envelope=envelope)
        policy = {**self.fixture.policy, "not_before": self.now - 2}
        with self.assertRaisesRegex(V.Refused, "NOT_ADOPTED"): self.bind(validation_policy=policy)

    def test_review_policy_expiry_and_identity_collision_refused(self):
        for value in ({**self.policy, "expires_at": self.now},
                      {**self.policy, "reviewer_ids": [201]},
                      {**self.policy, "merge_actor_id": 999},
                      {**self.policy, "schema_version": True}):
            with self.assertRaises(V.Refused): self.bind(review_policy=value)

    def test_closed_or_draft_pull_request_refused(self):
        for key, value in (("state", "closed"), ("draft", True), ("merged", True)):
            with self.subTest(key=key), self.assertRaises(V.Refused):
                self.bind(observed={**self.observed, key: value})

    def test_no_unrecognized_fields_or_boolean_ids(self):
        for value in ({**self.observed, "status_context": "success"},
                      {**self.observed, "repository_id": True}):
            with self.assertRaises(V.Refused): self.bind(observed=value)


if __name__ == "__main__": unittest.main()
