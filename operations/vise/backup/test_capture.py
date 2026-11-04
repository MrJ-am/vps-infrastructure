import os
from pathlib import Path
import tempfile
import unittest
import capture as C


class Files(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.owner = os.getuid()
        self.group = os.getgid()
        self.path = self.root / 'synthetic-ledger'
        self.path.write_bytes(b'invented account tombstone\n')
        self.path.chmod(0o600)

    def tearDown(self):
        self.temporary.cleanup()

    def read(self):
        fd, info = C.regular(self.path, self.owner, 1024, self.group)
        os.close(fd)
        return info

    def test_regular_private_file(self):
        self.assertEqual(self.read().st_size, 27)
        self.assertEqual(len(C.hash_private(self.path, self.owner, 1024, self.group)), 64)

    def test_public_file_refused(self):
        self.path.chmod(0o640)
        with self.assertRaises(C.Refused): self.read()

    def test_public_directory_refused(self):
        self.root.chmod(0o755)
        with self.assertRaises(C.Refused): self.read()

    def test_hardlink_refused(self):
        os.link(self.path, self.root / 'extra-link')
        with self.assertRaises(C.Refused): self.read()

    def test_symlink_refused(self):
        saved = self.path.with_suffix('.saved')
        self.path.rename(saved)
        self.path.symlink_to(saved)
        with self.assertRaises(OSError): self.read()

    def test_parent_symlink_refused(self):
        parent = self.root / 'real'
        parent.mkdir(mode=0o700)
        link = self.root / 'link'
        link.symlink_to(parent, target_is_directory=True)
        with self.assertRaises(OSError): C.directory(link, self.owner, self.group)

    def test_oversize_refused(self):
        with self.assertRaises(C.Refused): C.regular(self.path, self.owner, 1, self.group)

    def test_wrong_owner_refused(self):
        with self.assertRaises(C.Refused): C.regular(self.path, self.owner + 1, 1024)

    def test_fifo_refused_without_blocking(self):
        self.path.unlink()
        os.mkfifo(self.path, 0o600)
        with self.assertRaises(C.Refused): self.read()


if __name__ == '__main__':
    unittest.main()
