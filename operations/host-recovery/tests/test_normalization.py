"""Synthetic source-only relocation contracts. No Nix or shell execution."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("normalize_sources", Path(__file__).resolve().parents[1] / "normalize_sources.py")
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


class NormalizationTest(unittest.TestCase):
    def setUp(self):
        self.parser = tool.parser()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)

    def rewrite(self, code):
        return tool.rewrite("etc/nixos/configuration.nix", code.encode(),
                            {"root/bundle/module.nix"}, {"root", "root/bundle"}, self.parser)

    def test_absolute_paths_become_lexically_relative(self):
        result, refs, changes, _ = self.rewrite('{ imports = [ /root/bundle/module.nix ]; }')
        self.assertEqual(result, b'{ imports = [ ../../root/bundle/module.nix ]; }')
        self.assertEqual(refs[0]["kind"], "module-import-expression")
        self.assertEqual(changes[0]["target"], "root/bundle/module.nix")

    def test_string_source_paths_remain_anchored_strings(self):
        result, _, _, _ = self.rewrite('{ imports = [ "/root/bundle/module.nix" ]; }')
        self.assertIn(b'(toString ../../root/bundle/module.nix)', result)
        self.assertNotIn(b'"../../', result)

    def test_missing_reference_is_reported_without_reading_it(self):
        result, refs, changes, residual = self.rewrite('{ x = builtins.readFile /root/uncollected.json; }')
        self.assertEqual(result, b'{ x = builtins.readFile /root/uncollected.json; }')
        self.assertEqual(refs[0]["kind"], "builtins.readFile")
        self.assertFalse(refs[0]["available"])
        self.assertEqual(changes, [])
        self.assertEqual(len(residual), 1)

    def test_search_path_requires_explicit_pin(self):
        result, refs, changes, _ = self.rewrite('{ x = import <nixpkgs> {}; }')
        self.assertEqual(refs[0]["kind"], "search-path-requires-a-lock")
        self.assertEqual(changes, [])
        self.assertIn(b'<nixpkgs>', result)

    def test_default_argument_is_not_an_established_active_import(self):
        _, refs, _, _ = self.rewrite('{ module ? /root/missing/module.nix }: { imports = [ module ]; }')
        self.assertEqual(refs[0]["kind"], "function-default-not-necessarily-used")

    def test_comments_and_runtime_paths_are_not_rewritten(self):
        code = '# /root/bundle/module.nix\n{ script = \'\'cat /root/bundle/module.nix\'\'; runtime = "/var/lib/app"; }'
        result, refs, changes, residual = self.rewrite(code)
        self.assertEqual(result, code.encode())
        self.assertEqual((refs, changes), ([], []))
        self.assertEqual(len(residual), 2)

    def test_dynamic_paths_remain_unresolved(self):
        code = '{ x = "/root/${name}/module.nix"; }'
        result, refs, changes, residual = self.rewrite(code)
        self.assertEqual(result, code.encode())
        self.assertEqual((refs, changes), ([], []))
        self.assertTrue(residual)

    def test_directory_presence_does_not_claim_complete_contents(self):
        _, refs, _, _ = self.rewrite('{ x = builtins.path { path = /root/bundle; }; }')
        self.assertEqual(refs[0]["target_type"], "partial-directory")

    def test_invalid_nix_refused_before_output(self):
        with self.assertRaisesRegex(ValueError, "SOURCE_SYNTAX_ERROR"):
            self.rewrite('{ imports = [ /root/bundle/module.nix; }')

    def fixture(self):
        root = self.base / "input"
        source = root / "source/etc/nixos"
        source.mkdir(parents=True)
        raw = b'{ imports = [ /root/bundle/module.nix ]; }\n'
        (source / "configuration.nix").write_bytes(raw)
        target = root / "source/root/bundle"
        target.mkdir(parents=True)
        (target / "module.nix").write_bytes(b'{}\n')
        files = [{"path": str(p.relative_to(root / "source")), "bytes": p.stat().st_size,
                  "sha256": tool.digest(p.read_bytes()), "change": "unchanged"}
                 for p in sorted((root / "source").rglob("*.nix"))]
        review = {"files": files, "authority": "user-authorized-agent-reviewed-code-only-declaration",
                  "entrypoint": "etc/nixos/configuration.nix", "generation_binding": "unverified",
                  "declared_state_version": {"value": None, "source": None}}
        raw_review = json.dumps(review).encode()
        (root / "review.json").write_bytes(raw_review)
        return root, tool.digest(raw_review)

    def test_reproducible_tree_preserves_originals_and_scope(self):
        root, digest = self.fixture()
        before = {str(p): tool.digest(p.read_bytes()) for p in root.rglob("*") if p.is_file()}
        first = tool.normalize(root, digest, self.base / "first")
        second = tool.normalize(root, digest, self.base / "second")
        self.assertEqual(first, second)
        self.assertEqual(first["normalization_changes"], 1)
        self.assertFalse(first["evaluated"])
        self.assertFalse(first["activatable"])
        self.assertFalse(first["complete_dependency_graph"])
        self.assertEqual(before, {str(p): tool.digest(p.read_bytes()) for p in root.rglob("*") if p.is_file()})
        for p in (self.base / "first").rglob("*"):
            if p.is_file():
                self.assertEqual(p.read_bytes(), (self.base / "second" / p.relative_to(self.base / "first")).read_bytes())

    def test_manifest_or_source_tampering_refused(self):
        root, digest = self.fixture()
        with self.assertRaisesRegex(ValueError, "REVIEW_DIGEST_MISMATCH"):
            tool.normalize(root, "0" * 64, self.base / "output")
        (root / "source/root/bundle/module.nix").write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, "SOURCE_DIGEST_MISMATCH"):
            tool.normalize(root, digest, self.base / "output")
        self.assertFalse((self.base / "output").exists())

    def test_source_links_and_output_overwrite_refused(self):
        root, digest = self.fixture()
        source = root / "source/root/bundle/module.nix"
        source.unlink()
        source.symlink_to("/not-an-authorized-source")
        with self.assertRaisesRegex(ValueError, "LINKED_SOURCE"):
            tool.normalize(root, digest, self.base / "output")
        source.unlink()
        source.write_bytes(b'{}\n')
        (self.base / "output").mkdir()
        with self.assertRaises(FileExistsError):
            tool.normalize(root, digest, self.base / "output")

    def test_review_link_is_refused_before_reading_target(self):
        root, digest = self.fixture()
        (root / "review.json").unlink()
        (root / "review.json").symlink_to("/not-an-authorized-review")
        with self.assertRaisesRegex(ValueError, "LINKED_REVIEW"):
            tool.normalize(root, digest, self.base / "output")


if __name__ == "__main__":
    unittest.main()
