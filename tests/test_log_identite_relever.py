import base64
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('releve_identite', ROOT / 'scripts/log-identite-relever.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class ReleveIdentite(unittest.TestCase):
    def test_projection_sans_secret_et_base_inchangee(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'sessions.sqlite'
            plan = {'subject': '00000000-0000-4000-8000-000000000001',
                    'name': 'fixture-proprietaire', 'mail': 'Alice@example.test',
                    'client_secret': 'ne-jamais-projeter', 'intent': 'ne-jamais-projeter'}
            with sqlite3.connect(db) as c:
                c.execute('CREATE TABLE log_principaux(subject TEXT, mail TEXT)')
                c.execute('INSERT INTO log_principaux VALUES(?,?)', (plan['subject'], plan['mail'].lower()))
            avant = db.read_bytes()
            self.assertEqual(m.relever(plan, db), {'identifiant': 'fixture-proprietaire', 'mail': 'alice@example.test'})
            self.assertEqual(avant, db.read_bytes())
            with self.assertRaises(ValueError):
                m.relever(dict(plan, mail='autre@example.test'), db)
            with self.assertRaises(ValueError):
                m.relever(dict(plan, subject='00000000-0000-4000-8000-000000000002'), db)

    def test_chiffrement_reel_et_destinataire(self):
        with tempfile.TemporaryDirectory() as tmp:
            prive = Path(tmp) / 'private.pem'
            subprocess.run(['openssl', 'genpkey', '-algorithm', 'RSA', '-pkeyopt', 'rsa_keygen_bits:4096',
                '-out', str(prive)], check=True, capture_output=True)
            public = subprocess.check_output(['openssl', 'pkey', '-in', str(prive), '-pubout'])
            destinataire = base64.b64encode(public).decode()
            document = {'identifiant': 'fixture', 'mail': 'alice@example.test'}
            chiffre = m.chiffrer(document, destinataire)
            self.assertNotIn('alice', chiffre)
            clair = subprocess.check_output(['openssl', 'pkeyutl', '-decrypt', '-inkey', str(prive),
                '-pkeyopt', 'rsa_padding_mode:oaep', '-pkeyopt', 'rsa_oaep_md:sha256'],
                input=base64.b64decode(chiffre))
            self.assertEqual(json.loads(clair), document)
            with self.assertRaises(ValueError):
                m.chiffrer(document, base64.b64encode(b'cle invalide').decode())
            with self.assertRaises(ValueError):
                m.chiffrer({'mail': 'x' * 447}, destinataire)


if __name__ == '__main__':
    unittest.main()
