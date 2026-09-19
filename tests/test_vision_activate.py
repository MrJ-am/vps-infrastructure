import importlib.util
import os
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "vision_activate", ROOT / "scripts/vision-activate.py"
)
VISION_ACTIVATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VISION_ACTIVATE)


class CurrentLinkRollback(unittest.TestCase):
    def test_existing_link_is_detached_then_restored(self):
        with tempfile.TemporaryDirectory() as directory:
            current = Path(directory) / "current"
            current.symlink_to("releases/old")

            previous = VISION_ACTIVATE.detach_current_link(current)
            self.assertEqual(previous, "releases/old")
            self.assertFalse(current.is_symlink())

            current.symlink_to("releases/candidate")
            VISION_ACTIVATE.restore_current_link(current, previous)
            self.assertTrue(current.is_symlink())
            self.assertEqual(os.readlink(current), "releases/old")

    def test_candidate_link_is_removed_when_none_existed(self):
        with tempfile.TemporaryDirectory() as directory:
            current = Path(directory) / "current"

            previous = VISION_ACTIVATE.detach_current_link(current)
            self.assertIsNone(previous)
            current.symlink_to("releases/candidate")

            VISION_ACTIVATE.restore_current_link(current, previous)
            self.assertFalse(current.is_symlink())
            self.assertFalse(current.exists())

    def test_real_directory_is_never_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            current = Path(directory) / "current"
            current.mkdir()

            with self.assertRaisesRegex(RuntimeError, "sans être un lien"):
                VISION_ACTIVATE.detach_current_link(current)


if __name__ == "__main__":
    unittest.main()
