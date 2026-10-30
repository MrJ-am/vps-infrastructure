"""Contract checks with invented artifacts and metadata; no production access."""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

DIRECTORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DIRECTORY))
import release_plan as release


def sri(value):
    return "sha256-" + base64.b64encode(hashlib.sha256(value).digest()).decode()


def fixture(root, now=1000):
    files = {}
    for number, name in enumerate(sorted(release.FILES)):
        value = f"Entirely invented fixture {number}: {name}\n".encode()
        (root / name).write_bytes(value)
        files[name] = {"path": name, "sha256": hashlib.sha256(value).hexdigest(), "bytes": len(value)}
    generation = {"derivation": "/nix/store/" + "0" * 32 + "-synthetic-candidate.drv",
                  "output": "/nix/store/" + "1" * 32 + "-synthetic-candidate",
                  "nar_hash": sri((root / "generation_nar").read_bytes())}
    previous = {"derivation": "/nix/store/" + "2" * 32 + "-synthetic-previous.drv",
                "output": "/nix/store/" + "3" * 32 + "-synthetic-previous",
                "nar_hash": sri((root / "previous_generation_nar").read_bytes())}
    manifest = {"schema_version": 1, "target": "synthetic-vps", "mode": "ordinary",
                "sources": {name: {"commit": str(index + 1) * 40, "tree_sha256": str(index + 1) * 64}
                            for index, name in enumerate(sorted(release.SOURCES))},
                "files": files, "nix": generation, "previous_nix": previous,
                "rules_revision": "3" * 40, "required_checks": sorted(release.CHECKS),
                "migration": {"current_schema": 1, "resulting_schema": 2, "old_reads": [1, 2],
                              "old_writes": [1, 2], "new_reads": [1, 2], "new_writes": [1, 2],
                              "preserves_new_writes": True, "data_restore": "separate-reconciled-recovery-required"},
                "secret_references": {name: "ref:synthetic/" + name.replace("_", "-") for name in release.SECRET_REFS},
                "window": {"maximum_seconds": 10800, "abandon_after_seconds": 7200, "return_reserve_seconds": 3600}}
    manifest["rules_revision"] = manifest["sources"]["validation"]["commit"]
    observed = {"schema_version": 1, "target": "synthetic-vps", "authority": "unverified_observation",
                "active_manifest_sha256": "a" * 64, "generation": copy.deepcopy(previous), "schema": 1, "active_slot": "blue"}
    evidence = {"schema_version": 1, "scope": "synthetic-qualification", "authority": "unsigned-local-evidence",
                "manifest_sha256": release.digest(release.canonical(manifest)), "rules_revision": manifest["rules_revision"],
                "checks": {name: {"status": "passed", "receipt_sha256": "b" * 64} for name in release.CHECKS}}
    policy = {"schema_version": 1, "scope": "local-review-proposal", "target": "synthetic-vps",
              "manifest_sha256": evidence["manifest_sha256"], "evidence_sha256": release.digest(release.canonical(evidence)),
              "observed_sha256": release.digest(release.canonical(observed)), "rules_revision": manifest["rules_revision"],
              "not_before": now, "expires_at": now + 3600, "approval_reference": None, "deployment_freeze": True}
    return manifest, policy, observed, evidence


class ReleaseContract(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="mrjam-release-synthetic-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.manifest, self.policy, self.observed, self.evidence = fixture(self.root)

    def plan(self, now=1000):
        return release.prepare(self.manifest, self.policy, self.observed, self.evidence, self.root, now)

    def rebind(self):
        """Fixture-only change by test controller, not a candidate capability."""
        self.evidence["manifest_sha256"] = release.digest(release.canonical(self.manifest))
        self.policy["manifest_sha256"] = self.evidence["manifest_sha256"]
        self.policy["evidence_sha256"] = release.digest(release.canonical(self.evidence))
        self.policy["observed_sha256"] = release.digest(release.canonical(self.observed))

    def refused(self, code=None):
        with self.assertRaises(release.Refusal) as failure:
            self.plan()
        if code:
            self.assertEqual(failure.exception.code, code)

    def test_complete_dossier_is_only_a_frozen_review_plan(self):
        result = self.plan()
        self.assertEqual(result["decision"], "review-plan-prepared")
        self.assertFalse(result["production_authorized"])
        self.assertFalse(result["execution_supported"])
        self.assertIn("DEPLOYMENT_FREEZE", result["blocking_gates"])
        self.assertIn("APPROVAL_MISSING", result["blocking_gates"])
        self.assertEqual(result["new_generation"], self.manifest["nix"])
        self.assertEqual(result["previous_generation"], self.observed["generation"])

    def test_repeat_plan_is_identical_and_does_not_modify_inputs(self):
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        self.assertEqual(self.plan(), self.plan())
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.iterdir()})

    def test_already_current_state_produces_no_install_or_rollback(self):
        self.observed["active_manifest_sha256"] = self.policy["manifest_sha256"]
        self.observed["generation"] = copy.deepcopy(self.manifest["nix"])
        self.observed["schema"] = 2
        self.rebind()
        result = self.plan()
        self.assertEqual(result["decision"], "no-changes")
        self.assertEqual(result["actions"], [])
        self.assertEqual(result["rollback_actions"], [])

    def test_actual_same_size_artifact_substitution_is_refused(self):
        p = self.root / "server"
        p.write_bytes(b"x" * p.stat().st_size)
        self.refused("ARTIFACT_DIGEST_MISMATCH")

    def test_actual_truncated_artifact_is_refused(self):
        (self.root / "frontends").write_bytes(b"x")
        self.refused("ARTIFACT_SIZE_MISMATCH")

    def test_missing_artifact_is_refused(self):
        (self.root / "nix_lock").unlink()
        self.refused("ARTIFACT_UNAVAILABLE")

    def test_symlink_leaf_is_never_followed(self):
        (self.root / "server").rename(self.root / "hidden")
        (self.root / "server").symlink_to(self.root / "hidden")
        self.refused("ARTIFACT_UNAVAILABLE")

    def test_symlink_parent_is_never_followed(self):
        (self.root / "directory").mkdir()
        (self.root / "server").rename(self.root / "directory/server")
        (self.root / "alias").symlink_to(self.root / "directory")
        self.manifest["files"]["server"]["path"] = "alias/server"
        self.rebind()
        self.refused("ARTIFACT_UNAVAILABLE")

    def test_fifo_never_blocks_or_looks_like_an_artifact(self):
        (self.root / "server").unlink()
        os.mkfifo(self.root / "server")
        self.refused("ARTIFACT_TYPE_REFUSED")

    def test_traversal_is_refused_even_with_rebound_policy(self):
        self.manifest["files"]["server"]["path"] = "../outside"
        self.rebind()
        self.refused("ARTIFACT_PATH_REFUSED")

    def test_one_file_cannot_replace_two_artifact_roles(self):
        self.manifest["files"]["frontends"] = copy.deepcopy(self.manifest["files"]["server"])
        self.rebind()
        self.refused("ARTIFACT_ALIAS_REFUSED")

    def test_candidate_cannot_remove_a_required_artifact(self):
        del self.manifest["files"]["runtime_config"]
        self.rebind()
        self.refused()

    def test_candidate_cannot_skip_a_required_check(self):
        self.manifest["required_checks"].remove("restore")
        self.rebind()
        self.refused("CHECKS_MISMATCH")

    def test_missing_or_failed_check_is_not_a_qualification(self):
        self.evidence["checks"]["continuity"]["status"] = "failed"
        self.rebind()
        self.refused("QUALIFICATION_INCOMPLETE")

    def test_forged_success_field_is_refused(self):
        self.manifest["user_approved"] = True
        self.rebind()
        self.refused()

    def test_candidate_cannot_select_older_rules_against_external_selection(self):
        self.manifest["rules_revision"] = "f" * 40
        self.manifest["sources"]["validation"]["commit"] = "f" * 40
        self.evidence["rules_revision"] = "f" * 40
        self.rebind()
        self.refused("RULES_MISMATCH")

    def test_manifest_substitution_cannot_reuse_review_policy(self):
        self.manifest["sources"]["application"]["commit"] = "f" * 40
        self.refused("MANIFEST_MISMATCH")

    def test_same_approval_cannot_change_target(self):
        self.manifest["target"] = "mrjam-vps"
        self.refused("TARGET_MISMATCH")

    def test_replay_after_state_change_is_refused(self):
        self.observed["active_slot"] = "green"
        self.refused("OBSERVATION_CHANGED")

    def test_receipt_substitution_is_refused(self):
        self.evidence["checks"]["rust"]["receipt_sha256"] = "c" * 64
        self.refused("EVIDENCE_MISMATCH")

    def test_expired_and_future_review_windows_are_refused(self):
        with self.assertRaises(release.Refusal) as failure:
            self.plan(now=4600)
        self.assertEqual(failure.exception.code, "REVIEW_WINDOW_CLOSED")
        with self.assertRaises(release.Refusal):
            self.plan(now=999)

    def test_too_long_review_window_is_refused(self):
        self.policy["expires_at"] = 4601
        self.refused("INVALID_WINDOW")

    def test_nar_hash_is_bound_to_actual_archive_digest(self):
        self.manifest["nix"]["nar_hash"] = "sha256-" + base64.b64encode(b"x" * 32).decode()
        self.rebind()
        self.refused("NAR_DIGEST_MISMATCH")

    def test_previous_generation_substitution_is_refused(self):
        self.observed["generation"]["output"] = "/nix/store/" + "4" * 32 + "-different"
        self.rebind()
        self.refused("PREVIOUS_GENERATION_MISMATCH")

    def test_changed_schema_is_refused_before_plan(self):
        self.observed["schema"] = 3
        self.rebind()
        self.refused("SCHEMA_CHANGED")

    def test_rollback_requires_old_writer_to_accept_new_schema(self):
        self.manifest["migration"]["old_writes"] = [1]
        self.rebind()
        self.refused("ROLLBACK_SCHEMA_INCOMPATIBLE")

    def test_new_writes_cannot_be_discarded_by_generation_rollback(self):
        self.manifest["migration"]["preserves_new_writes"] = False
        self.rebind()
        self.refused("NEW_WRITES_NOT_PRESERVED")

    def test_data_restore_is_not_an_automatic_binary_rollback(self):
        self.manifest["migration"]["data_restore"] = "restore-old-backup"
        self.rebind()
        self.refused("DATA_RESTORE_REFUSED")

    def test_window_reserves_time_for_return(self):
        self.manifest["window"]["abandon_after_seconds"] = 10800
        self.rebind()
        self.refused("INVALID_WINDOW")

    def test_initial_plan_freezes_writers_and_takes_consistent_backup(self):
        self.manifest["mode"] = "initial"
        self.rebind()
        result = self.plan()
        actions = result["actions"]
        self.assertLess(actions.index("freeze_all_writers_and_workers"), actions.index("capture_consistent_backup_through_bounded_operator"))
        self.assertLess(actions.index("capture_consistent_backup_through_bounded_operator"), actions.index("apply_only_reviewed_compatible_migration_plan"))

    def test_ordinary_plan_requires_readiness_before_nginx_and_drain(self):
        actions = self.plan()["actions"]
        self.assertNotIn("freeze_all_writers_and_workers", actions)
        self.assertLess(actions.index("require_business_readiness_200"), actions.index("reload_nginx_gracefully"))
        self.assertLess(actions.index("reload_nginx_gracefully"), actions.index("drain_previous_slot_without_forced_termination"))

    def test_reference_alone_is_not_an_authenticated_approval(self):
        self.policy["approval_reference"] = "e" * 64
        result = self.plan()
        self.assertFalse(result["production_authorized"])
        self.assertIn("APPROVAL_REFERENCE_NOT_AUTHENTICATED", result["blocking_gates"])

    def test_local_policy_cannot_lift_deployment_freeze(self):
        self.policy["deployment_freeze"] = False
        self.refused("FREEZE_POLICY_REFUSED")

    def test_plaintext_secret_is_not_a_reference(self):
        self.manifest["secret_references"]["database"] = "SYNTHETIC_PRIVATE_MARKER"
        self.rebind()
        self.refused()

    def test_wrong_json_type_is_a_closed_refusal(self):
        self.manifest["target"] = []
        self.refused()

    def test_plan_exposes_unverified_relations_as_blockers(self):
        result = self.plan()
        self.assertEqual(result["previous_manifest_sha256"], self.observed["active_manifest_sha256"])
        for code in ("SOURCE_TREE_AND_COMMIT_RELATION_UNVERIFIED", "NIX_CLOSURE_IMPORT_AND_REFERENCES_UNVERIFIED", "RECEIPT_CONTENT_AND_RESULT_UNVERIFIED"):
            self.assertIn(code, result["blocking_gates"])


class InputBoundary(unittest.TestCase):
    def cli(self, arguments):
        result = subprocess.run([sys.executable, "-I", "-S", str(DIRECTORY / "release_plan.py"), *arguments], capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr, b"")
        self.assertNotIn(b"SYNTHETIC_PRIVATE_MARKER", result.stdout)
        self.assertFalse(json.loads(result.stdout)["production_authorized"])
        return json.loads(result.stdout)

    def test_cli_never_echoes_invalid_arguments(self):
        self.assertEqual(self.cli(["SYNTHETIC_PRIVATE_MARKER"])["code"], "INVALID_INVOCATION")

    def test_cli_never_echoes_input_paths(self):
        self.assertEqual(self.cli(["SYNTHETIC_PRIVATE_MARKER"] * 5)["code"], "INPUT_UNAVAILABLE")

    def test_input_fifo_does_not_wait_for_a_writer(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.fifo"
            os.mkfifo(path)
            self.assertEqual(self.cli([str(path)] * 5)["code"], "INPUT_UNAVAILABLE")

    def test_frozen_plan_through_isolated_python_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            values = fixture(root, now=int(time.time()))
            paths = []
            for index, value in enumerate(values):
                path = root / f"document-{index}.json"
                path.write_bytes(release.canonical(value))
                paths.append(str(path))
            result = subprocess.run([sys.executable, "-I", "-S", str(DIRECTORY / "release_plan.py"), *paths, str(root)], capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stderr, b"")
            self.assertFalse(json.loads(result.stdout)["production_authorized"])

    def test_incomplete_templates_are_not_valid_evidence(self):
        names = ("release-manifest", "release-policy", "release-observation", "release-evidence")
        paths = [str(DIRECTORY / "templates" / (name + ".json.in")) for name in names]
        self.assertEqual(self.cli([*paths, str(DIRECTORY)])["code"], "INVALID_INPUT")

    def test_duplicate_fields_are_rejected_before_information_loss(self):
        with self.assertRaises(release.Refusal) as failure:
            release.load(b'{"outer":{"x":1,"x":2}}')
        self.assertEqual(failure.exception.code, "DUPLICATE_FIELD")

    def test_document_size_float_and_nonfinite_are_rejected(self):
        for raw in (b" " * (release.MAX_DOCUMENT + 1), b'{"n":1.2}', b'{"n":NaN}'):
            with self.assertRaises(release.Refusal):
                release.load(raw)


if __name__ == "__main__":
    unittest.main()
