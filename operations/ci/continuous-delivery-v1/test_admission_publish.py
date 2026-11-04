"""Invented documents only; exercise real atomic links and interrupted writes."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import admission_publish as P


class Publication(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.digest = 'a'*64
        self.record = b'invented record'
        self.metadata = {f'{number:064x}.data': b'invented metadata' for number in range(8)}

    def tearDown(self):
        self.temp.cleanup()

    def publish(self):
        P.publish(self.root, self.digest, self.record, self.metadata, owner=os.getuid())

    def test_idempotent_immutable_publication(self):
        self.publish()
        self.publish()
        entry = self.root/(self.digest+'.json')
        self.assertEqual(entry.read_bytes(), self.record)
        self.assertEqual(entry.stat().st_mode & 0o777, 0o444)
        self.assertEqual(entry.stat().st_nlink, 1)

    def test_changed_document_never_replaces_record(self):
        self.publish()
        self.metadata[next(iter(self.metadata))] = b'changed'
        with self.assertRaises(ValueError): self.publish()
        self.assertEqual((self.root/(self.digest+'.json')).read_bytes(), self.record)

    def test_vise_seven_documents_requires_explicit_installed_count(self):
        self.metadata.pop(next(iter(self.metadata)))
        with self.assertRaises(ValueError):self.publish()
        self.assertFalse((self.root/(self.digest+'.json')).exists())
        for _ in range(2):
            P.publish(self.root,self.digest,self.record,self.metadata,owner=os.getuid(),document_count=7)
        self.assertEqual((self.root/(self.digest+'.json')).read_bytes(),self.record)

    def test_incomplete_or_extra_metadata_never_publishes(self):
        for count in (6,7,9,True):
            with self.assertRaises(ValueError):
                P.publish(self.root,self.digest,self.record,self.metadata,owner=os.getuid(),document_count=count)
            self.assertFalse((self.root/(self.digest+'.json')).exists())

    def test_symlink_metadata_directory_refused(self):
        other = self.root/'other'
        other.mkdir()
        (self.root/'metadata').symlink_to(other)
        with self.assertRaises(OSError): self.publish()
        self.assertFalse((self.root/(self.digest+'.json')).exists())
        self.assertEqual(list(other.iterdir()), [])

    def test_partial_metadata_does_not_publish_admission(self):
        original = P.immutable
        calls = 0
        def interrupted(*args):
            nonlocal calls
            calls += 1
            if calls == 4: raise OSError('invented interruption')
            return original(*args)
        with patch.object(P, 'immutable', interrupted):
            with self.assertRaises(OSError): self.publish()
        self.assertFalse((self.root/(self.digest+'.json')).exists())
        self.publish()
        self.assertTrue((self.root/(self.digest+'.json')).is_file())

    def test_interruption_after_link_is_recovered(self):
        self.publish()
        entry = self.root/(self.digest+'.json')
        temporary = self.root/('.publish-'+'c'*32)
        os.link(entry, temporary)
        self.publish()
        self.assertFalse(temporary.exists())
        self.assertEqual(entry.stat().st_nlink, 1)

    def test_unknown_file_preserved_unsafe_temporary_refused(self):
        marker = self.root/'unrelated'
        marker.write_bytes(b'preserve')
        temporary = self.root/('.publish-'+'d'*32)
        temporary.symlink_to(marker)
        with self.assertRaises(ValueError): self.publish()
        self.assertEqual(marker.read_bytes(), b'preserve')
        self.assertTrue(temporary.is_symlink())


if __name__ == '__main__': unittest.main()
