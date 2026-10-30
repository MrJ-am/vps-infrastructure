"""No remote access: settings snapshots and keys are completely synthetic."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import forgejo_plan as forge
import release_plan as release


def fixture():
    repository = {"private": True, "default_branch": "main", "actions_enabled": False,
                  "protection": {"branch": "main", "required_checks": ["mrjam/independent-validation"],
                                 "minimum_reviews": 1, "force_push": False, "deletion": False, "administrator_bypass": False}}
    runner = {"enabled": False, "repository": "mrjam-validation", "label": "mrjam-synthetic-isolated",
              "ephemeral": True, "privileged": False, "docker_socket": False, "production_mounts": [],
              "production_network": False, "signing_credentials": False, "registration_secret_ref": "ref:forgejo/runner-registration",
              "maximum_jobs": 1, "qualification_profile": "synthetic-unqualified-for-vps"}
    desired = {"schema_version": 1, "scope": "prepared-not-adopted", "target": "forge.mrj.am", "deployment_freeze": True,
               "accepted_flow": "forgejo-main-to-github-mirror", "proposal_flow": "github-proposal-to-forgejo-review",
               "rules_revision": "a" * 40, "controller_revision": "b" * 40,
               "repositories": {name: copy.deepcopy(repository) for name in forge.REPOSITORIES}, "runner": runner}
    observed = {"schema_version": 1, "scope": "managed-settings-only", "target": "forge.mrj.am", "authority": "unverified_observation",
                "revision": "c" * 64, "repositories": {}, "runner": None}
    return desired, observed


class ForgejoPlanContract(unittest.TestCase):
    def setUp(self):
        self.desired, self.observed = fixture()

    def plan(self, expected=None):
        return forge.prepare(self.desired, self.observed, expected or release.digest(release.canonical(self.observed)))

    def refused(self, code):
        with self.assertRaises(release.Refusal) as error:
            self.plan()
        self.assertEqual(error.exception.code, code)

    def test_missing_managed_objects_produce_only_bounded_creation_proposals(self):
        plan = self.plan()
        self.assertFalse(plan["production_authorized"])
        self.assertFalse(plan["execution_supported"])
        self.assertEqual(len(plan["changes"]), 4)
        self.assertEqual(plan["deletions"], [])
        self.assertEqual(plan["unmanaged_objects"], "untouched")

    def test_equal_snapshot_is_idempotent_without_writes(self):
        self.observed["repositories"] = copy.deepcopy(self.desired["repositories"])
        self.observed["runner"] = copy.deepcopy(self.desired["runner"])
        self.assertEqual(self.plan()["changes"], [])
        self.assertEqual(self.plan()["decision"], "no-changes")

    def test_only_different_managed_field_is_proposed(self):
        self.observed["repositories"] = copy.deepcopy(self.desired["repositories"])
        self.observed["runner"] = copy.deepcopy(self.desired["runner"])
        self.observed["repositories"]["mrjam-plateforme"]["protection"]["minimum_reviews"] = 0
        changes = self.plan()["changes"]
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["operation"], "set_managed_repository_field")
        self.assertEqual(changes[0]["field"], "protection")

    def test_changed_snapshot_cannot_reuse_old_plan(self):
        old_digest = release.digest(release.canonical(self.observed))
        self.observed["revision"] = "d" * 64
        with self.assertRaises(release.Refusal) as error:
            self.plan(old_digest)
        self.assertEqual(error.exception.code, "OBSERVATION_CHANGED")

    def test_public_repository_is_not_silently_privatized(self):
        self.observed["repositories"] = copy.deepcopy(self.desired["repositories"])
        self.observed["repositories"]["mrjam-validation"]["private"] = False
        self.refused("PUBLIC_REPOSITORY_ADOPTION_REQUIRES_SEPARATE_REVIEW")

    def test_candidate_repository_cannot_host_privileged_validation_runner(self):
        self.desired["runner"]["repository"] = "mrjam-plateforme"
        self.refused("INVALID_INPUT")

    def test_candidate_cannot_enable_actions_or_runner_during_freeze(self):
        for target, field in ((self.desired["runner"], "enabled"), (self.desired["repositories"]["mrjam-validation"], "actions_enabled")):
            target[field] = True
            self.refused("DEPLOYMENT_FREEZE")
            target[field] = False

    def test_unsafe_executor_capabilities_are_refused(self):
        for field in ("privileged", "docker_socket", "production_network", "signing_credentials"):
            self.desired["runner"][field] = True
            self.refused("UNSAFE_RUNNER_REFUSED")
            self.desired["runner"][field] = False

    def test_protected_branch_cannot_allow_bypass_force_push_or_deletion(self):
        for field in ("force_push", "deletion", "administrator_bypass"):
            self.desired["repositories"]["mrjam-plateforme"]["protection"][field] = True
            self.refused("PROTECTION_WEAKENING_REFUSED")
            self.desired["repositories"]["mrjam-plateforme"]["protection"][field] = False

    def test_mandatory_independent_check_cannot_be_replaced(self):
        self.desired["repositories"]["mrjam-plateforme"]["protection"]["required_checks"] = ["candidate/success"]
        self.refused("REQUIRED_CHECKS_REFUSED")

    def test_two_authoritative_main_branches_are_refused(self):
        self.desired["accepted_flow"] = "bidirectional-main"
        self.refused("COMPETING_AUTHORITY_REFUSED")

    def test_arbitrary_fields_and_repositories_are_refused(self):
        self.desired["repositories"]["extra"] = copy.deepcopy(self.desired["repositories"]["mrjam-plateforme"])
        self.refused("INVALID_INPUT")

    def test_plan_does_not_mutate_the_snapshot(self):
        before = copy.deepcopy(self.observed)
        first = self.plan()
        self.assertEqual(self.observed, before)
        self.assertEqual(first, self.plan())

    def test_cli_works_with_environment_and_site_imports_disabled(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            desired_path, observed_path = root / "desired.json", root / "observed.json"
            desired_path.write_bytes(release.canonical(self.desired))
            observed_path.write_bytes(release.canonical(self.observed))
            result = subprocess.run([sys.executable, "-I", "-S", str(Path(forge.__file__)), str(desired_path), str(observed_path), release.digest(release.canonical(self.observed))], capture_output=True, timeout=5, cwd=root)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stderr, b"")
            self.assertFalse(json.loads(result.stdout)["production_authorized"])

    def test_cli_does_not_leak_path_on_missing_document(self):
        result = subprocess.run([sys.executable, "-I", "-S", str(Path(forge.__file__)), "SYNTHETIC_PRIVATE_MARKER", "missing", "f" * 64], capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr, b"")
        self.assertNotIn(b"SYNTHETIC_PRIVATE_MARKER", result.stdout)
        self.assertEqual(json.loads(result.stdout)["code"], "INPUT_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
