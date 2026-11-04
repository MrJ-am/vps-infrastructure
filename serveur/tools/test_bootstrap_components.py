"""Synthetic Git objects and refusal cases only: every fetch is forbidden here."""

from pathlib import Path
import os
import tempfile
import unittest

import bootstrap_components as bootstrap


TOOLS = Path(__file__).absolute().parent
MODULES = b'''[submodule "vision"]
    path = serveur/components/vision
    url = https://forge.mrj.am/MrJ-am/vision.git
[submodule "mateval"]
    path = serveur/components/mateval
    url = https://forge.mrj.am/MrJ-am/matheval.git
'''


class NoFetchGit(bootstrap.Git):
    def __init__(self):
        self.fetch_attempts = 0

    def run(self, directory, *arguments, **kwargs):
        if any(arg in {"fetch", "clone", "pull", "push", "submodule"} for arg in arguments):
            self.fetch_attempts += 1
            raise AssertionError("NETWORK_COMMAND_FORBIDDEN_IN_SYNTHETIC_TEST")
        return super().run(directory, *arguments, **kwargs)


def init(git, directory):
    directory.mkdir(parents=True)
    git.run(directory, "init", "--quiet", "--template=", "--initial-branch=synthetic")


def commit(git, directory, message="synthetic-fixture"):
    git.run(directory, "-c", "user.name=Synthetic Bootstrap", "-c", "user.email=synthetic@example.invalid", "commit", "--quiet", "-m", message)
    return bootstrap.text(git.run(directory, "rev-parse", "HEAD"))


class ParserTests(unittest.TestCase):
    def refused(self, code, callback, *args):
        with self.assertRaisesRegex(bootstrap.Refused, "^" + code + "$"):
            callback(*args)

    def test_only_exact_two_urls_and_paths_are_accepted(self):
        self.assertEqual(bootstrap.parse_modules(MODULES), bootstrap.URLS)
        self.refused("GITMODULES_PATH_OR_URL_MISMATCH", bootstrap.parse_modules,
                     MODULES.replace(b"MrJ-am/vision.git", b"another/repository.git"))
        self.refused("GITMODULES_PATH_OR_URL_MISMATCH", bootstrap.parse_modules,
                     MODULES.replace(b"https://forge.mrj.am/", b"https://credential@forge.mrj.am/"))

    def test_branch_and_custom_update_are_refused(self):
        for extra in [b"    branch = main\n", b"    update = !an-external-command\n", b"    shallow = true\n"]:
            self.refused("GITMODULES_OPTIONS_REFUSED", bootstrap.parse_modules, MODULES + extra)

    def test_duplicate_or_extra_sections_are_refused(self):
        self.refused("INVALID_GITMODULES", bootstrap.parse_modules, MODULES + MODULES)
        self.refused("GITMODULES_PATH_OR_URL_MISMATCH", bootstrap.parse_modules,
                     MODULES + b'[submodule "other"]\npath = other\nurl = https://github.com/other/repo.git\n')

    def test_tree_paths_modes_and_hashes_are_checked(self):
        raw = b"160000 commit " + b"a" * 40 + b"\tserveur/components/vision\0"
        self.assertEqual(bootstrap.parse_tree(raw)["serveur/components/vision"], ("160000", "commit", "a" * 40))
        for bad in [raw[:-1], raw + raw, raw.replace(b"serveur/components/vision", b"../escape"), raw.replace(b"a" * 40, b"main")]:
            with self.assertRaises(bootstrap.Refused):
                bootstrap.parse_tree(bad)

    def test_fetch_plan_contains_only_exact_sha_and_no_branch_or_recursive_update(self):
        component = bootstrap.Component("serveur/components/vision", bootstrap.URLS["serveur/components/vision"], "c" * 40, "initialize-fetch-checkout")
        self.assertEqual(bootstrap.fetch_arguments(component), (
            "fetch", "--depth=1", "--no-tags", "--no-recurse-submodules", "--no-write-fetch-head",
            "https://forge.mrj.am/MrJ-am/vision.git", "c" * 40,
        ))
        for commit_id in ["main", "c" * 7, "c" * 64, "-unsafe"]:
            with self.assertRaises(bootstrap.Refused):
                bootstrap.fetch_arguments(bootstrap.Component(component.path, component.url, commit_id, component.action))


class GitFixtureTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix=".bootstrap-test-", dir=TOOLS)
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / "platform"
        self.git = NoFetchGit()
        init(self.git, self.root)
        (self.root / ".gitmodules").write_bytes(MODULES)
        self.git.run(self.root, "add", ".gitmodules")
        self.pins = {}
        for path in bootstrap.URLS:
            source = self.base / path.rsplit("/", 1)[-1]
            init(self.git, source)
            (source / "synthetic.txt").write_text("Entirely synthetic bootstrap fixture.\n")
            self.git.run(source, "add", "synthetic.txt")
            self.pins[path] = commit(self.git, source)
            self.git.run(self.root, "update-index", "--add", "--cacheinfo", "160000," + self.pins[path] + "," + path)
        self.parent = commit(self.git, self.root)

    def tearDown(self):
        self.assertEqual(self.git.fetch_attempts, 0)

    def refused(self, code, callback, *args):
        with self.assertRaisesRegex(bootstrap.Refused, "^" + code + "$"):
            callback(*args)

    def present(self, path="serveur/components/vision", *, url=None, detach=True, symlink=False):
        target = self.root / path
        init(self.git, target)
        if symlink:
            (target / "synthetic-link").symlink_to("synthetic.txt")
        (target / "synthetic.txt").write_text("Entirely synthetic bootstrap fixture.\n")
        self.git.run(target, "add", ".")
        oid = commit(self.git, target)
        self.git.run(target, "config", "--local", "remote.origin.url", url or bootstrap.URLS[path])
        if detach:
            self.git.run(target, "checkout", "--quiet", "--detach", oid)
        self.pins[path] = oid
        self.git.run(self.root, "update-index", "--add", "--cacheinfo", "160000," + oid + "," + path)
        # Commit only when the synthetic child's hash differs from the initial pin.
        if self.git.run(self.root, "diff", "--cached", "--name-only"):
            self.parent = commit(self.git, self.root)
        return target

    def test_missing_components_plan_does_not_create_or_fetch(self):
        plan = bootstrap.make_plan(self.root, self.git)
        self.assertEqual(plan.superproject_commit, self.parent)
        self.assertEqual({item.path: item.commit for item in plan.components}, self.pins)
        self.assertTrue(all(item.action == "initialize-fetch-checkout" for item in plan.components))
        self.assertFalse((self.root / "components").exists())

    def test_empty_gitlink_directory_is_planned_without_mutation(self):
        target = self.root / "serveur/components/vision"
        target.mkdir(parents=True)
        bootstrap.make_plan(self.root, self.git)
        self.assertEqual(list(target.iterdir()), [])

    def test_empty_initialization_can_be_resumed_without_touching_work(self):
        target = self.root / "serveur/components/vision"
        init(self.git, target)
        self.git.run(target, "symbolic-ref", "HEAD", "refs/heads/bootstrap-unused")
        self.git.run(target, "config", "--local", "remote.origin.url", bootstrap.URLS["serveur/components/vision"])
        plan = bootstrap.make_plan(self.root, self.git)
        vision = next(item for item in plan.components if item.path == "serveur/components/vision")
        self.assertEqual(vision.action, "fetch-checkout-initialized-empty")
        self.assertEqual([p.name for p in target.iterdir()], [".git"])

    def test_clean_detached_present_component_is_verified_without_fetch(self):
        self.present()
        plan = bootstrap.make_plan(self.root, self.git)
        present = next(item for item in plan.components if item.path == "serveur/components/vision")
        self.assertEqual(present.action, "verify-only")
        self.assertRegex(present.tree, r"^[a-f0-9]{40}$")

    def test_both_existing_components_apply_is_read_only(self):
        self.present("serveur/components/vision")
        self.present("serveur/components/mateval")
        plan = bootstrap.make_plan(self.root, self.git)
        result = bootstrap.apply_plan(self.root, plan, self.git)
        self.assertEqual([item["action"] for item in result], ["verified-existing", "verified-existing"])
        self.assertEqual(bootstrap.make_plan(self.root, self.git), plan)

    def test_plan_does_not_refresh_an_existing_index(self):
        target = self.present()
        index = target / ".git/index"
        before = index.read_bytes()
        tracked = target / "synthetic.txt"
        metadata = tracked.stat()
        os.utime(tracked, ns=(metadata.st_atime_ns, metadata.st_mtime_ns + 10_000_000_000))
        bootstrap.make_plan(self.root, self.git)
        self.assertEqual(index.read_bytes(), before)

    def test_remote_divergence_is_refused(self):
        self.present(url="https://github.com/other/repository.git")
        self.refused("COMPONENT_REMOTE_URL_MISMATCH", bootstrap.make_plan, self.root, self.git)

    def test_attached_branch_is_refused(self):
        self.present(detach=False)
        self.refused("COMPONENT_DETACHED_HEAD_REQUIRED", bootstrap.make_plan, self.root, self.git)

    def test_existing_component_at_another_commit_is_not_moved(self):
        target = self.present()
        (target / "synthetic.txt").write_text("A second synthetic change.\n")
        self.git.run(target, "add", "synthetic.txt")
        changed = commit(self.git, target)
        self.refused("COMPONENT_HEAD_MISMATCH", bootstrap.make_plan, self.root, self.git)
        self.assertEqual(bootstrap.text(self.git.run(target, "rev-parse", "HEAD")), changed)

    def test_dirty_or_ignored_files_are_preserved_and_refused(self):
        target = self.present()
        (target / "untracked.txt").write_text("Keep this local work.\n")
        self.refused("COMPONENT_NOT_CLEAN", bootstrap.make_plan, self.root, self.git)
        self.assertEqual((target / "untracked.txt").read_text(), "Keep this local work.\n")
        (target / "untracked.txt").unlink()
        (target / ".git/info").mkdir()
        (target / ".git/info/exclude").write_text("ignored.txt\n")
        (target / "ignored.txt").write_text("Keep this ignored file.\n")
        self.refused("COMPONENT_NOT_CLEAN", bootstrap.make_plan, self.root, self.git)

    def test_nonempty_directory_without_git_is_refused(self):
        target = self.root / "serveur/components/vision"
        target.mkdir(parents=True)
        (target / "work.txt").write_text("Existing work.\n")
        self.refused("NONEMPTY_COMPONENT_WITHOUT_GIT", bootstrap.make_plan, self.root, self.git)

    def test_component_directory_symlink_is_refused(self):
        (self.root / "serveur/components").mkdir(parents=True)
        (self.root / "serveur/components/vision").symlink_to(self.base / "vision", target_is_directory=True)
        self.refused("SYMLINK_PATH_REFUSED", bootstrap.make_plan, self.root, self.git)

    def test_tracked_symlink_in_pinned_tree_is_refused(self):
        self.present(symlink=True)
        self.refused("COMPONENT_SYMLINK_OR_NESTED_GITLINK_REFUSED", bootstrap.make_plan, self.root, self.git)

    def test_local_transport_rewrite_is_refused(self):
        target = self.present()
        self.git.run(target, "config", "--local", "url.https://other.invalid/.insteadOf", "https://github.com/")
        self.refused("LOCAL_GIT_TRANSPORT_CONFIGURATION_REFUSED", bootstrap.make_plan, self.root, self.git)

    def test_partial_clone_cannot_trigger_an_implicit_fetch(self):
        target = self.present()
        self.git.run(target, "config", "--local", "remote.origin.promisor", "true")
        self.refused("PARTIAL_OR_SPARSE_REPOSITORY_REFUSED", bootstrap.make_plan, self.root, self.git)
        self.assertEqual(bootstrap.git_environment()["GIT_NO_LAZY_FETCH"], "1")

    def test_external_object_alternates_are_refused(self):
        target = self.present()
        (target / ".git/objects/info").mkdir(exist_ok=True)
        (target / ".git/objects/info/alternates").write_text(str(self.base / "vision/.git/objects") + "\n")
        self.refused("EXTERNAL_OBJECT_SOURCE_REFUSED", bootstrap.make_plan, self.root, self.git)

    def test_changed_parent_plan_refuses_before_fetch_or_directory_creation(self):
        plan = bootstrap.make_plan(self.root, self.git)
        (self.root / "new.txt").write_text("Another synthetic parent commit.\n")
        self.git.run(self.root, "add", "new.txt")
        commit(self.git, self.root)
        self.refused("PLAN_CHANGED", bootstrap.apply_plan, self.root, plan, self.git)
        self.assertFalse((self.root / "components").exists())

    def test_dirty_superproject_is_refused(self):
        (self.root / ".gitmodules").write_bytes(MODULES + b"\n# local edit\n")
        self.refused("SUPERPROJECT_NOT_CLEAN", bootstrap.make_plan, self.root, self.git)

    def test_extra_gitlink_is_refused(self):
        self.git.run(self.root, "update-index", "--add", "--cacheinfo", "160000," + self.pins["serveur/components/vision"] + ",other")
        commit(self.git, self.root)
        self.refused("GITLINK_SET_MISMATCH", bootstrap.make_plan, self.root, self.git)


if __name__ == "__main__":
    unittest.main()
