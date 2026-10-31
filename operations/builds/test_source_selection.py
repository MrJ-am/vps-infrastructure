#!/usr/bin/env python3
"""Independent fixtures for exact-source selection and unchanged-Elm reuse."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import prepare
import reuse_frontend
import select_sources


class Sources(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.platform = Path(self.temporary.name) / "platform"
        self.vision = self.platform / "components/vision"
        self.mateval = self.platform / "components/mateval"
        for repo in (self.platform, self.vision, self.mateval):
            repo.mkdir(parents=True, exist_ok=True)
            self.git(repo, "init", "--quiet")
            self.git(repo, "config", "user.name", "Synthetic Fixture")
            self.git(repo, "config", "user.email", "fixture@example.invalid")
            (repo / "Cargo.toml").write_text("synthetic manifest\n")
        self.write(self.platform, "crates/server/src/main.rs", "fn main() {}\n")
        self.write(self.platform, "crates/log/src/lib.rs", "pub fn synthetic() {}\n")
        self.write(self.vision, "src/lib.rs", "pub fn synthetic() {}\n")
        self.write(self.mateval, "src/lib.rs", "pub fn synthetic() {}\n")
        self.write(self.mateval, "frontend/site/index.html", "synthetic frontend\n")
        self.vision_commit = self.commit(self.vision)
        self.mateval_commit = self.commit(self.mateval)
        self.write(self.platform, ".gitmodules", "synthetic gitlink metadata\n")
        self.platform_commit = self.commit(self.platform)
        self.frontend_files = {"frontend/site/index.html": prepare.digest(b"synthetic frontend\n")}
        self.baseline = {"sources": {"mateval": {"commit": self.mateval_commit, "files": self.frontend_files}}}

    def git(self, repo, *args):
        return subprocess.check_output(["git", "-c", "core.hooksPath=/dev/null", "-C", str(repo), *args], stderr=subprocess.DEVNULL, text=True).strip()

    def write(self, repo, name, value):
        file = repo / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(value)

    def commit(self, repo):
        self.git(repo, "add", ".")
        self.git(repo, "commit", "--quiet", "-m", "synthetic source")
        return self.git(repo, "rev-parse", "HEAD")

    def test_lock_is_derived_from_commit_bytes_not_loose_content(self):
        self.write(self.platform, "crates/server/src/main.rs", "tampered loose file\n")
        lock = select_sources.propose(self.platform, self.platform_commit, self.baseline)
        self.assertEqual(lock["sources"]["platform"]["files"]["crates/server/src/main.rs"], prepare.digest(b"fn main() {}\n"))
        with self.assertRaisesRegex(prepare.Refused, "SOURCE_HASH_MISMATCH"):
            prepare.verify_sources(self.platform, lock)

    def test_untracked_and_excluded_categories_never_enter_lock(self):
        self.write(self.platform, "crates/server/src/untracked.rs", "not committed\n")
        self.write(self.platform, "private/fixture.txt", "SYNTHETIC_EXCLUDED_MARKER\n")
        lock = select_sources.propose(self.platform, self.platform_commit, self.baseline)
        self.assertNotIn("crates/server/src/untracked.rs", lock["sources"]["platform"]["files"])
        self.assertNotIn("private/fixture.txt", lock["sources"]["platform"]["files"])
        self.assertIn("crates/log/src/lib.rs", lock["sources"]["platform"]["files"])

    def test_nonexact_revision_rejected(self):
        for revision in ("HEAD", "main", "--help", "a" * 39, "A" * 40):
            with self.subTest(revision=revision), self.assertRaisesRegex(prepare.Refused, "EXACT_SOURCE_COMMIT_REQUIRED"):
                select_sources.propose(self.platform, revision, self.baseline)

    def test_gitlink_must_match_checked_out_component(self):
        self.write(self.vision, "src/next.rs", "pub fn next() {}\n")
        self.commit(self.vision)
        with self.assertRaisesRegex(prepare.Refused, "SOURCE_CHECKOUT_COMMIT_MISMATCH"):
            select_sources.propose(self.platform, self.platform_commit, self.baseline)

    def test_tracked_source_symlink_rejected_without_reading_target(self):
        (self.platform / "crates/server/src/link.rs").symlink_to("/does-not-exist")
        revision = self.commit(self.platform)
        with self.assertRaisesRegex(prepare.Refused, "SOURCE_GIT_FILE_TYPE_REFUSED"):
            select_sources.propose(self.platform, revision, self.baseline)

    def test_rust_only_change_preserves_frontend_build_identity(self):
        self.write(self.mateval, "src/lib.rs", "pub fn changed() {}\n")
        current = self.commit(self.mateval)
        proof = reuse_frontend.equivalent(self.mateval, self.mateval_commit, current, self.frontend_files)
        self.assertEqual(proof["current_component_commit"], current)
        self.assertEqual(proof["frontend_build_commit_retained"], self.mateval_commit)

    def test_changed_or_new_frontend_file_refuses_reuse(self):
        for path in ("frontend/site/index.html", "frontend/site/new.js"):
            with self.subTest(path=path):
                self.write(self.mateval, path, "changed frontend\n")
                current = self.commit(self.mateval)
                with self.assertRaisesRegex(prepare.Refused, "FRONTEND_TREE_CHANGED"):
                    reuse_frontend.equivalent(self.mateval, self.mateval_commit, current, self.frontend_files)

    def test_dirty_frontend_cannot_be_hidden_by_unchanged_git_tree(self):
        self.write(self.mateval, "frontend/site/index.html", "loose mutation\n")
        with self.assertRaisesRegex(prepare.Refused, "SOURCE_HASH_MISMATCH"):
            reuse_frontend.equivalent(self.mateval, self.mateval_commit, self.mateval_commit, self.frontend_files)


if __name__ == "__main__":
    unittest.main()
