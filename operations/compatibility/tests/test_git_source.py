import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("git_source", Path(__file__).resolve().parents[1] / "verify_git_source.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PublicSource(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "source"
        self.root.mkdir()
        self.gitdir = Path(self.temp.name) / "objects.git"
        self.environment = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL="/dev/null")
        subprocess.run(["git", "init", "--quiet", "--bare", str(self.gitdir)], env=self.environment, check=True)

    def expected(self):
        command = ["git", "--git-dir=" + str(self.gitdir), "--work-tree=" + str(self.root),
                   "-c", "core.autocrlf=false", "-c", "core.fileMode=true"]
        subprocess.run([*command, "add", "--all", "--force"], env=self.environment, check=True)
        return subprocess.check_output([*command, "write-tree"], env=self.environment).decode().strip()

    def test_git_order_modes_and_symbolic_link_object(self):
        (self.root / "a").mkdir()
        (self.root / "a/version").write_text("26.05")
        (self.root / "a.c").write_text("synthetic")
        (self.root / ".version").symlink_to("a/version")
        script = self.root / "executable"
        script.write_text("synthetic, never executed")
        script.chmod(0o755)
        result = module.verify(self.root, self.expected())
        self.assertEqual(result["symlinks"], 1)
        self.assertEqual(result["files"], 3)

    def test_broken_symlink_is_hashed_without_reading_its_target(self):
        (self.root / "link").symlink_to("synthetic-missing")
        module.verify(self.root, self.expected())

    def test_content_executable_mode_and_link_substitutions_are_rejected(self):
        regular = self.root / "code"
        regular.write_bytes(b"fixed")
        link = self.root / "link"
        link.symlink_to("code")
        expected = self.expected()
        for mutation in ["content", "mode", "link"]:
            with self.subTest(mutation=mutation):
                regular.write_bytes(b"other" if mutation == "content" else b"fixed")
                regular.chmod(0o755 if mutation == "mode" else 0o644)
                link.unlink()
                link.symlink_to("elsewhere" if mutation == "link" else "code")
                with self.assertRaisesRegex(ValueError, "SOURCE_TREE_MISMATCH"):
                    module.verify(self.root, expected)

    def test_fifo_refused_without_reading(self):
        os.mkfifo(self.root / "pipe")
        with self.assertRaisesRegex(ValueError, "SOURCE_TYPE_REFUSED"):
            module.verify(self.root, "1" * 40)


if __name__ == "__main__":
    unittest.main()
