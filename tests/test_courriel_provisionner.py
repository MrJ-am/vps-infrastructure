"""Installation idempotente, refus de rotation et protection des secrets."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('provision', Path(__file__).resolve().parents[1] / 'scripts/courriel-provisionner.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Provisionnement(unittest.TestCase):
    def test_installation_privee_rejeu_rotation_refusee(self):
        with tempfile.TemporaryDirectory() as root:
            rapport = module.installer(root, 'A' * 16)
            self.assertFalse(rapport['secret_affiche'])
            p = Path(root) / 'proton-smtp.json'
            self.assertEqual(p.stat().st_mode & 0o777, 0o600)
            contenu = p.read_bytes()
            self.assertEqual(module.installer(root, 'A' * 16)['installation'], 'deja_presente')
            with self.assertRaises(ValueError): module.installer(root, 'B' * 16)
            self.assertEqual(contenu, p.read_bytes())

    def test_destination_non_privee_et_liens_refuses(self):
        with tempfile.TemporaryDirectory() as root:
            Path(root).chmod(0o755)
            with self.assertRaises(ValueError): module.installer(root, 'A' * 16)
            Path(root).chmod(0o700)
            autre = Path(root) / 'autre'; autre.mkdir(mode=0o700)
            lien = Path(root) / 'lien'; lien.symlink_to(autre)
            with self.assertRaises(ValueError): module.installer(lien, 'A' * 16)
            (Path(root) / 'proton-smtp.json').symlink_to(autre / 'inexistant')
            with self.assertRaises(OSError): module.installer(root, 'A' * 16)

    def test_qualification_uniquement_boite_propre_et_piece_chiffree(self):
        with tempfile.TemporaryDirectory() as root:
            module.installer(root, 'A' * 16)
            # La cryptographie réelle est qualifiée dans les tests de restauration.
            with patch.object(module.subprocess, 'run') as age, patch.object(module.courriel, 'transmettre') as transport:
                age.return_value.stdout = b'age-encryption.org/v1\nqualification'
                rapport = module.qualifier(root, 'age1' + 'a' * 58)
                config, message = transport.call_args.args
                self.assertEqual(message['To'], config['from_address'])
                self.assertEqual(message['From'], config['from_address'])
                self.assertEqual(list(message.iter_attachments())[0].get_payload(decode=True), age.return_value.stdout)
                self.assertEqual(rapport['presence_en_boite'], 'a_verifier')
                self.assertTrue(json.loads(age.call_args.kwargs['input'])['qualification_smtp'])
