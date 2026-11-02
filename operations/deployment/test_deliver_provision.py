"""Invented delivery bytes only; never import or modify the host's Nix store."""
import hashlib
import fcntl
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import deliver_provision as m


def release(payload=b'INVENTED_EXPORT'):
    package='/nix/store/'+'0'*32+'-mrjam-kanidm-worker-provision-2'
    unit='/nix/store/'+'1'*32+'-unit-mrjam-kanidm-worker-provision.service'
    return {'schema_version':1,'export_sha256':hashlib.sha256(payload).hexdigest(),
            'export_bytes':len(payload),'store_paths':[package,unit],
            'required_free_bytes':1024**3+4*len(payload),
            'package':package,'unit_store':unit,'unit_sha256':'0'*64}


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.fd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY)
        self.addCleanup(os.close,self.fd)

    def test_validated_exact_payload_is_private_and_replayable(self):
        for _ in range(2):
            m.receive(io.BytesIO(b'INVENTED_EXPORT'),self.fd,release())
            self.assertEqual((self.root/'export.nar').read_bytes(),b'INVENTED_EXPORT')
            self.assertEqual((self.root/'export.nar').stat().st_mode&0o777,0o600)
            self.assertFalse((self.root/'export.partial').exists())

    def test_corruption_truncation_or_extra_bytes_never_publishes(self):
        for payload in (b'INVENTED_EXPORU',b'INVENTED',b'INVENTED_EXPORT_EXTRA'):
            with self.assertRaises(m.Refused):
                m.receive(io.BytesIO(payload),self.fd,release())
            self.assertFalse((self.root/'export.nar').exists())

    def test_interrupted_transfer_cannot_change_an_existing_verified_export(self):
        m.receive(io.BytesIO(b'INVENTED_EXPORT'),self.fd,release())
        with self.assertRaises(m.Refused):
            m.receive(io.BytesIO(b'PARTIAL'),self.fd,release())
        self.assertEqual((self.root/'export.nar').read_bytes(),b'INVENTED_EXPORT')
        m.receive(io.BytesIO(b'INVENTED_EXPORT'),self.fd,release())
        self.assertFalse((self.root/'export.partial').exists())

    def test_partial_symlink_hardlink_and_public_permissions_refused_before_truncate(self):
        outside=self.root/'untouched';outside.write_bytes(b'KEEP');outside.chmod(0o600)
        partial=self.root/'export.partial'
        for kind in ('symlink','hardlink','public'):
            if kind=='symlink': partial.symlink_to(outside)
            elif kind=='hardlink': os.link(outside,partial)
            else: partial.write_bytes(b'KEEP');partial.chmod(0o644)
            with self.assertRaises((OSError,m.Refused)):
                m.receive(io.BytesIO(b'INVENTED_EXPORT'),self.fd,release())
            self.assertEqual(outside.read_bytes(),b'KEEP')
            partial.unlink()

    def test_unit_installation_is_exact_and_never_overwrites_a_foreign_unit(self):
        target=Path(release()['unit_store'])/m.UNIT
        m.install_unit(self.fd,target)
        m.install_unit(self.fd,target)
        self.assertEqual(os.readlink(self.root/m.UNIT),str(target))
        with self.assertRaises(m.Refused):
            m.install_unit(self.fd,Path('/different/unit'))
        self.assertEqual(os.readlink(self.root/m.UNIT),str(target))

    def test_existing_regular_unit_is_not_replaced(self):
        (self.root/m.UNIT).write_text('KEEP')
        with self.assertRaises(OSError):
            m.install_unit(self.fd,Path(release()['unit_store'])/m.UNIT)
        self.assertEqual((self.root/m.UNIT).read_text(),'KEEP')

    def test_manifest_cannot_select_another_package_path_or_unbounded_payload(self):
        self.assertEqual(m.validate_release(release()),release())
        for field,value in [('package','/tmp/program'),('schema_version',True),('export_bytes',True),
                            ('export_bytes',8*1024**3),('export_sha256','x'*64),
                            ('store_paths',[release()['package']]*2),('unit_store','/tmp/unit')]:
            document=release();document[field]=value
            with self.assertRaises(m.Refused):m.validate_release(document)

    def test_unsealed_template_refuses_before_creating_directories(self):
        with patch.object(m,'protected_directory') as directory:
            with self.assertRaises(m.Refused):m.deliver(None,io.BytesIO(b''))
            directory.assert_not_called()

    def test_generation_mismatch_refuses_before_receiving_bytes(self):
        with patch.object(m.os,'geteuid',return_value=0),patch.object(m.os.path,'realpath',return_value='/other'), \
                patch.object(m,'protected_directory') as directory:
            with self.assertRaises(m.Refused):m.deliver(release(),io.BytesIO(b''))
            directory.assert_not_called()

    def test_concurrent_delivery_cannot_reach_receive_or_truncate(self):
        fcntl.flock(self.fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        second=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY)
        with patch.object(m.os,'geteuid',return_value=0),patch.object(m.os.path,'realpath',return_value=m.PREVIOUS), \
                patch.object(m,'protected_directory',return_value=second),patch.object(m,'receive') as receive:
            with self.assertRaises(BlockingIOError):m.deliver(release(),io.BytesIO(b''))
            receive.assert_not_called()


if __name__=='__main__':
    unittest.main()
