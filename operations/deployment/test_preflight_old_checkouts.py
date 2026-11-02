import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import preflight_old_checkouts as m


class OldCheckoutTests(unittest.TestCase):
    def test_every_location_is_a_previously_received_source_directory(self):
        received=Path(__file__).resolve().parents[1]/"received/20261101/vps-reviewed-sources/extracted/source"
        self.assertEqual(len(m.CHECKOUTS),17)
        self.assertEqual(len({row[1] for row in m.CHECKOUTS}),17)
        for label,location,repository in m.CHECKOUTS:
            self.assertRegex(label,r"^catalogue-[0-9]{2}$")
            self.assertIn(repository,m.EXPECTED)
            self.assertTrue((received/location.lstrip("/")).is_dir())

    def test_normal_checkout_metadata_is_observed_without_reading_worktree(self):
        with tempfile.TemporaryDirectory() as directory:
            git="/etc/profiles/per-user/jam/bin/git"
            subprocess.run([git,"init","--initial-branch=main",directory],stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True,
                           env={"GIT_CONFIG_NOSYSTEM":"1","GIT_CONFIG_GLOBAL":"/dev/null","HOME":"/nonexistent"})
            (Path(directory)/"INVENTED_PRIVATE_CONTENT").write_text("must never be read")
            value=m.inspect_repository(Path(directory)/".git",{"invented":"a"*40},git=git,
                validate=lambda path:m.require(path.is_dir() and not path.is_symlink()),
                tree_validate=lambda path:m.historical_tree(path,owners=(0,os.getuid())))
            self.assertTrue(value["exists"])
            self.assertFalse(value["bare"])
            self.assertFalse(value["non_empty"])


if __name__=="__main__":unittest.main()
