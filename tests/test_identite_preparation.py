"""Clés immuables, fichiers privés et refus sans divulgation de leur contenu."""
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('preparer_identite', ROOT / 'scripts/identite-preparer.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
MODELE = ROOT / 'operations/identite/realm.json'
SMTP = {'host': 'smtp.protonmail.ch', 'port': 587, 'username': 'qualification@example.test',
        'password': 'JetonSynthetique123', 'from_address': 'qualification@example.test',
        'starttls_required': True, 'certificate_verification': True}


class ImportPrive(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def snapshot(self):
        return {p.name: (p.read_bytes(), p.stat().st_ino, p.stat().st_mtime_ns)
                for p in self.root.iterdir() if p.is_file()}

    def test_preparation_et_relance_sans_rotation_ni_modification(self):
        smtp = self.root / 'smtp.json'; smtp.write_text(json.dumps(SMTP)); smtp.chmod(0o600)
        r = m.preparer(MODELE, self.root, smtp)
        self.assertFalse(r['import_existant_verifie'])
        avant = self.snapshot()
        self.assertTrue(m.preparer(MODELE, self.root, smtp)['import_existant_verifie'])
        self.assertTrue(m.preparer(MODELE, self.root, smtp, controler=True)['import_existant_verifie'])
        self.assertEqual(avant, self.snapshot())
        for p in self.root.iterdir(): self.assertEqual(p.stat().st_mode & 0o777, 0o600)
        realm = json.loads((self.root / 'mrjam-realm.json').read_text())
        self.assertFalse(realm['registrationAllowed'])
        self.assertEqual(len(realm['users']), 3)
        self.assertTrue(all(u.get('serviceAccountClientId') for u in realm['users']))
        self.assertEqual(realm['smtpServer']['starttls'], 'true')
        self.assertEqual(len(set((self.root / p).read_text() for p in m.SECRETS)), 5)

    def test_reprise_partielle_garde_la_cle_deja_creee(self):
        p = self.root / m.SECRETS[0]; p.write_text('a' * 43); p.chmod(0o600)
        inode = p.stat().st_ino
        m.preparer(MODELE, self.root)
        self.assertEqual(p.read_text(), 'a' * 43); self.assertEqual(p.stat().st_ino, inode)

    def test_lien_symbolique_et_lien_physique_refuses_sans_modifier_la_cible(self):
        for type_lien in ('symbolique', 'physique'):
            with self.subTest(type_lien=type_lien), tempfile.TemporaryDirectory() as ailleurs:
                cible = Path(ailleurs) / 'prive'; cible.write_text('a' * 43); cible.chmod(0o600)
                p = self.root / m.SECRETS[0]
                if type_lien == 'symbolique': p.symlink_to(cible)
                else: os.link(cible, p)
                try:
                    with self.assertRaises((ValueError, OSError)): m.preparer(MODELE, self.root)
                    self.assertEqual(cible.read_text(), 'a' * 43)
                    self.assertFalse((self.root / m.SECRETS[1]).exists())
                finally: p.unlink()

    def test_dossier_par_un_parent_symbolique_refuse(self):
        lien = self.root / 'lien'; lien.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError): m.preparer(MODELE, lien / 'destination')
        self.assertFalse((self.root / 'destination').exists())

    def test_permissions_faibles_fifo_et_fichier_trop_grand_refuses(self):
        p = self.root / m.SECRETS[0]
        p.write_text('a' * 43); p.chmod(0o644)
        with self.assertRaises(ValueError): m.preparer(MODELE, self.root)
        p.unlink(); os.mkfifo(p, 0o600)
        with self.assertRaises(ValueError): m.preparer(MODELE, self.root)
        p.unlink(); p.write_text('a' * 513); p.chmod(0o600)
        with self.assertRaises(ValueError): m.preparer(MODELE, self.root)
        self.assertFalse((self.root / m.SECRETS[1]).exists())

    def test_import_modifie_ou_secret_manquant_refuses_sans_ecrasement(self):
        m.preparer(MODELE, self.root)
        p = self.root / 'mrjam-realm.json'; realm = json.loads(p.read_text())
        realm['registrationAllowed'] = True; p.write_text(json.dumps(realm))
        avant = self.snapshot()
        with self.assertRaises(ValueError): m.preparer(MODELE, self.root)
        self.assertEqual(avant, self.snapshot())
        (self.root / m.SECRETS[-1]).unlink()
        with self.assertRaises(ValueError): m.preparer(MODELE, self.root)
        self.assertFalse((self.root / m.SECRETS[-1]).exists())

    def test_verification_seule_ne_cree_pas_de_fichier(self):
        with self.assertRaises(FileNotFoundError): m.preparer(MODELE, self.root, controler=True)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_preparations_concurrentes_refusees(self):
        p = self.root / '.preparation.lock'
        fd = os.open(p, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(ValueError): m.preparer(MODELE, self.root)
            self.assertFalse((self.root / m.SECRETS[0]).exists())
        finally: os.close(fd)

    def test_erreur_cli_ne_divulgue_pas_le_faux_secret(self):
        p = self.root / 'mrjam-realm.json'
        p.write_text('{"faux_secret": "DONNEE_PERSONNELLE_NE_PAS_PUBLIER"'); p.chmod(0o600)
        r = subprocess.run([sys.executable, str(ROOT / 'scripts/identite-preparer.py'),
            '--modele', str(MODELE), '--destination', str(self.root)], capture_output=True)
        self.assertEqual(r.returncode, 1)
        self.assertNotIn(b'DONNEE_PERSONNELLE', r.stdout + r.stderr)
        self.assertNotIn(b'Traceback', r.stderr)
        self.assertEqual(r.stdout, b'')


if __name__ == '__main__': unittest.main()
