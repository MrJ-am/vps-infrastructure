"""Un diagnostic fermé ne restitue ni secret, ni contenu ou chemin arbitraire."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('audit_unix', ROOT / 'scripts/vision-identite-unix-auditer.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


class Diagnostic(unittest.TestCase):
    def test_refus_lanceur_sans_afficher_son_chemin(self):
        texte = '/bin/sh: /run/mrjam-q-source-' + m.REVISION[:12] + '/postgresql.sh: Permission denied\n'
        r = m.classer(texte)
        self.assertEqual(r['categories'], ['permission_refusee', 'lanceur_postgresql_non_traversable'])
        self.assertNotIn('/run/', json.dumps(r))

    def test_secret_nom_et_erreur_inconnue_absents(self):
        texte = 'mon secret FICTIF-XZ09 ; dossier /root/contenu-personnel ; courriel prive@example.invalid\n'
        r = m.classer(texte)
        self.assertEqual(r, dict(categories=[], contenu_affiche=False))
        for valeur in ('FICTIF-XZ09', '/root/', 'personnel', 'example.invalid'): self.assertNotIn(valeur, json.dumps(r))
        self.assertEqual(m.classer(texte + 'FATAL: ' + texte)['categories'], ['postgresql_fatal'])

    def test_autre_revision_pas_de_diagnostic_lanceur_attribue(self):
        r = m.classer('/bin/sh: /run/mrjam-q-source-ffffffffffff/postgresql.sh: Permission denied')
        self.assertEqual(r['categories'], ['permission_refusee'])

    def test_fichier_public_lien_et_trop_grand_refuses(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'journal'; p.write_text('privé'); p.chmod(0o600)
            self.assertEqual(m.lire(p), 'privé')
            p.chmod(0o644)
            with self.assertRaises(ValueError): m.lire(p)
            p.chmod(0o600); lien = Path(d) / 'lien'; lien.symlink_to(p)
            with self.assertRaises(OSError): m.lire(lien)
            p.write_bytes(b'x' * 262145)
            with self.assertRaises(ValueError): m.lire(p)


if __name__ == '__main__': unittest.main()
