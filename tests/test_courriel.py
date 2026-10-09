"""La file survit aux erreurs SMTP et ne déclare jamais une réception finale."""
import importlib.util
import json
import os
from pathlib import Path
import smtplib
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('courriel', Path(__file__).resolve().parents[1] / 'services/mrjam-courriel/courriel.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
CONFIG = dict(host='smtp.protonmail.ch', port=587, username='synthetique@example.test',
              password='JetonSynthetique123', from_address='synthetique@example.test',
              starttls_required=True, certificate_verification=True)


class Courriels(unittest.TestCase):
    def test_file_durable_reprise_et_deduplication(self):
        with tempfile.TemporaryDirectory() as root:
            envoyes = []
            def transport(config, message):
                if not envoyes:
                    envoyes.append('erreur')
                    raise smtplib.SMTPServerDisconnected('ne pas conserver adresse ou secret')
                envoyes.append(message['Message-ID'])
            file = module.FileCourriel(Path(root) / 'file.sqlite', CONFIG['from_address'], transport)
            file.ajouter('preavis:1', 'personne@example.test', 'Préavis', 'Texte fixe')
            file.traiter(CONFIG, 100)
            self.assertEqual(file.etat('preavis:1')['etat'], 'attente')
            self.assertEqual(file.etat('preavis:1')['erreur'], 'relais_indisponible')
            file = module.FileCourriel(Path(root) / 'file.sqlite', CONFIG['from_address'], transport)
            self.assertEqual(file.traiter(CONFIG, 159), 0)
            self.assertEqual(file.traiter(CONFIG, 160), 1)
            self.assertEqual(file.etat('preavis:1')['etat'], 'accepte_relais')
            file.ajouter('preavis:1', 'personne@example.test', 'Préavis', 'Texte fixe')
            self.assertEqual(file.traiter(CONFIG, 1000), 0)
            self.assertEqual(len(envoyes), 2)
            file.purger(160+31*86400)
            with file.ouvrir() as db:
                self.assertEqual(db.execute('SELECT length(message) FROM courriels').fetchone()[0],0)
            file.ajouter('preavis:1', 'personne@example.test', 'Préavis', 'Texte fixe')
            self.assertEqual(file.traiter(CONFIG, 160+31*86400),0)
            with self.assertRaises(ValueError):
                file.ajouter('preavis:1', 'autre@example.test', 'Préavis', 'Texte fixe')
            self.assertEqual((Path(root) / 'file.sqlite').stat().st_mode & 0o077, 0)

    def test_tls_certificat_et_ordre_authentification(self):
        with patch.object(module.smtplib, 'SMTP') as smtp:
            relais = smtp.return_value.__enter__.return_value
            relais.send_message.return_value = {}
            module.transmettre(CONFIG, module.EmailMessage())
            self.assertEqual([c[0] for c in relais.method_calls], ['ehlo', 'starttls', 'ehlo', 'login', 'send_message'])
            contexte = relais.starttls.call_args.kwargs['context']
            self.assertTrue(contexte.check_hostname)
            self.assertEqual(contexte.verify_mode, module.ssl.CERT_REQUIRED)
            relais.starttls.side_effect = smtplib.SMTPNotSupportedError('STARTTLS absent')
            relais.reset_mock()
            with self.assertRaises(smtplib.SMTPNotSupportedError):
                module.transmettre(CONFIG, module.EmailMessage())
            relais.login.assert_not_called()

    def test_secret_prive_configuration_et_injection_entetes(self):
        with tempfile.TemporaryDirectory() as root:
            p = Path(root) / 'smtp.json'
            p.write_text(json.dumps(CONFIG)); p.chmod(0o600)
            self.assertEqual(module.verifier_smtp(module.lire_prive(p)), CONFIG)
            p.chmod(0o644)
            with self.assertRaises(ValueError): module.lire_prive(p)
            lien = Path(root) / 'lien'; lien.symlink_to(p)
            with self.assertRaises(OSError): module.lire_prive(lien)
            for champ in ('starttls_required', 'certificate_verification'):
                with self.assertRaises(ValueError): module.verifier_smtp({**CONFIG, champ: False})
            file = module.FileCourriel(Path(root) / 'file.sqlite', CONFIG['from_address'])
            with self.assertRaises(ValueError): file.ajouter('x', 'a@example.test\nBcc: b@example.test', 'Sujet', 'Texte')

    def test_annulation_empeche_un_envoi_en_attente(self):
        with tempfile.TemporaryDirectory() as root:
            transport=unittest.mock.Mock()
            file=module.FileCourriel(Path(root)/'file.sqlite',CONFIG['from_address'],transport)
            file.ajouter('preavis:annule','personne@example.test','Préavis','Texte fixe')
            file.annuler('preavis:annule')
            self.assertEqual(file.traiter(CONFIG),0)
            transport.assert_not_called()


if __name__ == '__main__': unittest.main()
