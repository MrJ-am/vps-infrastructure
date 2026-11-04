import hashlib
import os
from pathlib import Path
import tempfile
import unittest
import capture as C
import envelope as E
import retention as R


class Retention(unittest.TestCase):
    NOW = 1800000000

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def pair(self, number, days):
        name = format(number, '032x')
        directory = self.root / name
        directory.mkdir(mode=0o700)
        hashes = {}
        for filename in ['components.tar.age', 'key.age']:
            raw = b'invented ciphertext for retention fixture'
            (directory / filename).write_bytes(raw)
            (directory / filename).chmod(0o600)
            hashes[filename] = hashlib.sha256(raw).hexdigest()
        E.write_json(directory / 'manifest.json', {'schema_version': 1,
            'kind': 'vise-paired-backup', 'capture_id': name,
            'created': self.NOW - days * 86400, 'components': list(E.FILES),
            'offline_pair': True, 'requires_current_erasure_journal': True, 'files': hashes})
        return name

    def prune(self, latest):
        return R.prune(self.root, latest, owner=os.getuid(), group=os.getgid(), now=self.NOW)

    def test_thirty_days_and_two_verified_pairs_retained(self):
        old = self.pair(1, 90)
        second = self.pair(2, 60)
        latest = self.pair(3, 0)
        self.assertEqual(self.prune(latest), 1)
        self.assertFalse((self.root / old).exists())
        self.assertTrue((self.root / second).exists())
        self.assertTrue((self.root / latest).exists())

    def test_recent_pairs_not_removed(self):
        for number, days in [(1, 29), (2, 20), (3, 10)]: self.pair(number, days)
        latest = self.pair(4, 0)
        self.assertEqual(self.prune(latest), 0)

    def test_unknown_partial_and_corrupt_pairs_preserved(self):
        old = self.pair(1, 90)
        (self.root / old / 'components.tar.age').write_bytes(b'corrupt')
        self.pair(2, 60)
        latest = self.pair(3, 0)
        (self.root / '.incomplete.pending').mkdir(mode=0o700)
        (self.root / 'legacy.tar').write_bytes(b'legacy synthetic data')
        self.assertEqual(self.prune(latest), 0)
        self.assertTrue((self.root / old).exists())
        self.assertTrue((self.root / '.incomplete.pending').exists())
        self.assertTrue((self.root / 'legacy.tar').exists())

    def test_no_pruning_without_fresh_valid_publication(self):
        old = self.pair(1, 90)
        self.pair(2, 60)
        latest = self.pair(3, 2)
        with self.assertRaises(C.Refused): self.prune(latest)
        self.assertTrue((self.root / old).exists())

    def test_latest_corruption_prevents_any_deletion(self):
        old = self.pair(1, 90)
        self.pair(2, 60)
        latest = self.pair(3, 0)
        (self.root / latest / 'key.age').write_bytes(b'bad key ciphertext')
        with self.assertRaises(C.Refused): self.prune(latest)
        self.assertTrue((self.root / old).exists())


if __name__ == '__main__': unittest.main()
