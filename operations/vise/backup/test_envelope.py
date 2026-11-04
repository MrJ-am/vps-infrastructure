import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
import capture as C
import envelope as E


class Encryption(unittest.TestCase):
    def setUp(self):
        self.tools = json.loads(os.environ['VISE_BACKUP_TEST_TOOLS'])
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.backups = self.root / 'backups'
        self.backups.mkdir(mode=0o700)
        self.identifier = 'a' * 32
        self.work = self.backups / ('.' + self.identifier + '.pending')
        self.work.mkdir(mode=0o700)
        self.source = self.work / 'components'
        self.source.mkdir(mode=0o700)
        self.data = {'database.dump': b'invented database image\n',
                     'deletions.log': b'invented deletion ledger\n'}
        for name, raw in self.data.items():
            (self.source / name).write_bytes(raw)
            (self.source / name).chmod(0o600)
        self.key = self.root / 'synthetic-recipient-key'
        subprocess.run([self.tools['age_keygen'], '-o', str(self.key)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        self.recipient = subprocess.check_output([self.tools['age_keygen'], '-y', str(self.key)],
                                                 stderr=subprocess.DEVNULL, text=True).strip()

    def tearDown(self):
        self.temporary.cleanup()

    def envelope(self, cls=E.Envelope):
        return cls(self.tools, os.getuid(), os.getgid())

    def test_actual_ciphertext_decrypts_with_recipient_to_exact_pair(self):
        target = self.envelope().publish(self.backups, self.identifier, self.recipient)
        self.assertEqual({p.name for p in target.iterdir()},
                         {'components.tar.age', 'key.age', 'manifest.json'})
        self.assertFalse(self.work.exists())
        recovered_key = self.root / 'recovered-key'
        subprocess.run([self.tools['age'], '-d', '-i', str(self.key), '-o', str(recovered_key),
                        str(target / 'key.age')], stderr=subprocess.DEVNULL, check=True)
        raw = subprocess.check_output([self.tools['age'], '-d', '-i', str(recovered_key),
                                       str(target / 'components.tar.age')], stderr=subprocess.DEVNULL)
        with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
            self.assertEqual(set(archive.getnames()), set(self.data))
            for name, expected in self.data.items():
                self.assertEqual(archive.extractfile(name).read(), expected)
        document = json.loads((target / 'manifest.json').read_text())
        self.assertTrue(document['offline_pair'])
        self.assertTrue(document['requires_current_erasure_journal'])
        for name, digest in document['files'].items():
            self.assertEqual(self.envelope().digest(target / name), digest)

    def test_corrupt_decryption_does_not_publish(self):
        class Corrupt(E.Envelope):
            def run(self, args, output=None):
                super().run(args, output)
                if '-d' in args:
                    Path(args[args.index('-o') + 1]).write_bytes(b'corrupted synthetic result')
        with self.assertRaises(C.Refused):
            self.envelope(Corrupt).publish(self.backups, self.identifier, self.recipient)
        self.assertFalse((self.backups / self.identifier).exists())
        self.assertTrue(self.work.exists())

    def test_existing_publication_is_preserved(self):
        target = self.backups / self.identifier
        target.mkdir(mode=0o700)
        (target / 'sentinel').write_bytes(b'existing synthetic backup')
        with self.assertRaises(C.Refused):
            self.envelope().publish(self.backups, self.identifier, self.recipient)
        self.assertEqual((target / 'sentinel').read_bytes(), b'existing synthetic backup')

    def test_unknown_component_refused_before_encryption(self):
        (self.source / 'unexpected').write_bytes(b'invented')
        with self.assertRaises(C.Refused):
            self.envelope().publish(self.backups, self.identifier, self.recipient)
        self.assertEqual({p.name for p in self.work.iterdir()}, {'components'})


if __name__ == '__main__':
    unittest.main()
