"""Pas de tiers, pas de rotation ; remise ambiguë jamais réessayée."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('telephone', ROOT/'scripts/vision-telephone.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
spec = importlib.util.spec_from_file_location('plan_telephone', ROOT/'scripts/vision-plan.py')
plan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plan)
CONFIG = dict(host='smtp.protonmail.ch', port=587, username='automath@mrj.am',
    from_address='automath@mrj.am', password='A'*16, starttls_required=True, certificate_verification=True)


class Telephone(unittest.TestCase):
    def test_phase_fermee(self):
        self.assertEqual(plan.verifier(dict(version=1, action='vision-telephone')), 'vision-telephone')
        with self.assertRaises(ValueError):
            plan.verifier(dict(version=1, action='vision-telephone', recipient='tiers'))

    def test_message_propre_temoin_sans_personne(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/'operation'
            with patch.object(m.courriel, 'lire_prive', return_value=CONFIG), patch.object(m.subprocess, 'run') as age, patch.object(m.courriel, 'transmettre') as smtp:
                age.return_value.stdout = b'age-encryption.org/v1\ntemoin'
                r = m.envoyer(root, Path('/existant'))
                self.assertEqual(age.call_args.args[0], ['age','-r',m.RECIPIENT])
                payload = json.loads(age.call_args.kwargs['input'])
                self.assertEqual(payload['reference'], m.REFERENCE)
                self.assertTrue(payload['qualification_telephone'])
                config, message = smtp.call_args.args
                self.assertEqual(message['To'], CONFIG['from_address'])
                self.assertEqual(list(message.iter_attachments())[0].get_filename(), m.PIECE)
                self.assertFalse(r['sauvegarde_reelle'])
                self.assertEqual(r['dechiffrement'], 'a_verifier')
            with patch.object(m.courriel, 'transmettre') as smtp:
                self.assertTrue(m.envoyer(root, Path('/existant'))['deja_transmis'])
                smtp.assert_not_called()

    def test_remise_ambigue_bloque_rejeu_sans_fuite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/'operation'
            with patch.object(m.courriel, 'lire_prive', return_value=CONFIG), patch.object(m.subprocess, 'run') as age, patch.object(m.courriel, 'transmettre', side_effect=RuntimeError('detail-prive')):
                age.return_value.stdout = b'age-encryption.org/v1\ntemoin'
                with self.assertRaises(RuntimeError): m.envoyer(root, Path('/existant'))
            self.assertTrue((root/'intention.json').exists())
            self.assertFalse((root/'accepte.json').exists())
            with patch.object(m.courriel, 'transmettre') as smtp:
                with self.assertRaises(ValueError): m.envoyer(root, Path('/existant'))
                smtp.assert_not_called()

    def test_droits_liens_et_boite_divergente_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/'operation'
            root.mkdir(mode=0o755)
            with self.assertRaises(ValueError): m.envoyer(root, Path('/existant'))
            root.chmod(0o700)
            with patch.object(m.courriel, 'lire_prive', return_value=dict(CONFIG, username='tiers@example.test', from_address='tiers@example.test')), patch.object(m.courriel, 'transmettre') as smtp:
                with self.assertRaises(ValueError): m.envoyer(root, Path('/existant'))
                smtp.assert_not_called()
            autre = Path(tmp)/'autre'; autre.mkdir(mode=0o700)
            lien = Path(tmp)/'lien'; lien.symlink_to(autre)
            with self.assertRaises(ValueError): m.envoyer(lien, Path('/existant'))
