"""Copies durables sur fixtures privées, sans base ni service de production."""
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    'sauvegarde_monolithe', Path(__file__).resolve().parents[1] / 'scripts/monolithe-sauvegarde.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CopiesDurables(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.racine = Path(self.tmp.name)

    def test_sqlite_blob_zero_absence_et_unicode(self):
        source, cible = self.racine / 'source.sqlite', self.racine / 'copie.sqlite'
        lignes = [(1, b'\x00\xff\r\n', 0, 'épreuve 😀'), (2, b'', None, None)]
        with sqlite3.connect(source) as db:
            db.execute('CREATE TABLE temoin(id INTEGER PRIMARY KEY, message BLOB, valeur INTEGER, texte TEXT)')
            db.executemany('INSERT INTO temoin VALUES(?,?,?,?)', lignes)
        source.chmod(0o600)
        module.copie_sqlite(source, cible)
        with sqlite3.connect(cible) as db:
            self.assertEqual(db.execute('SELECT * FROM temoin ORDER BY id').fetchall(), lignes)
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone(), ('ok',))
        self.assertEqual(cible.stat().st_mode & 0o777, 0o600)

    def test_sqlite_lien_et_fichier_public_refuses(self):
        source = self.racine / 'source.sqlite'
        with sqlite3.connect(source) as db:
            db.execute('CREATE TABLE temoin(id INTEGER)')
        source.chmod(0o600)
        lien = self.racine / 'lien.sqlite'
        lien.symlink_to(source)
        with self.assertRaises(ValueError):
            module.copie_sqlite(lien, self.racine / 'refuse.sqlite')
        source.chmod(0o644)
        with self.assertRaises(ValueError):
            module.copie_sqlite(source, self.racine / 'refuse.sqlite')

    def test_registre_conserve_exactement_les_intentions(self):
        source, cible = self.racine / 'intents.jsonl', self.racine / 'copie.jsonl'
        contenu = ''.join(json.dumps(v, ensure_ascii=False) + '\n' for v in [
            {'version': 2, 'etat': 'demande', 'id': 'synthetique', 'date': '2026-10-11T01:02:03Z'},
            {'version': 2, 'etat': 'annule', 'raison': 'épreuve 😀'}]).encode()
        source.write_bytes(contenu)
        source.chmod(0o600)
        module.copie_registre(source, cible)
        self.assertEqual(cible.read_bytes(), contenu)

    def test_registre_corrompu_lien_et_public_refuses(self):
        source = self.racine / 'intents.jsonl'
        source.write_bytes(b'{"incomplet":')
        source.chmod(0o600)
        with self.assertRaises(ValueError):
            module.copie_registre(source, self.racine / 'refuse.jsonl')
        self.assertFalse((self.racine / 'refuse.jsonl').exists())
        source.write_bytes(b'[]\n')
        with self.assertRaises(ValueError):
            module.copie_registre(source, self.racine / 'refuse.jsonl')
        lien = self.racine / 'lien.jsonl'
        lien.symlink_to(source)
        with self.assertRaises(OSError):
            module.copie_registre(lien, self.racine / 'refuse.jsonl')
        source.write_bytes(b'{}\n')
        source.chmod(0o644)
        with self.assertRaises(ValueError):
            module.copie_registre(source, self.racine / 'refuse.jsonl')


if __name__ == '__main__':
    unittest.main()
