"""Le diagnostic de build ne restitue aucun fragment de son entrée."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('audit_construction', Path(__file__).resolve().parents[1] /
    'scripts/vision-identite-construction-auditer.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


class Diagnostic(unittest.TestCase):
    def test_compilation_classee_sans_source_ni_nom_prive(self):
        texte = ('/source/CompteSecret.java:22: error: cannot find symbol\n'
            '    String secret="contenu-personnel";\n'
            "error: builder for '/nix/store/" + 'a' * 32 + "-mrjam-keycloak-26.7.3.drv' failed with exit code 1\n")
        r = m.classer(texte)
        self.assertEqual(r['categories'], ['symbole_java_absent'])
        self.assertEqual(r['builders_refuses'], ['spi_mrjam'])
        self.assertNotIn('Secret', json.dumps(r)); self.assertNotIn('personnel', json.dumps(r))

    def test_refus_inconnu_reste_sans_texte(self):
        self.assertEqual(m.classer('error: message inconnu et valeur-secrete\n'),
            dict(categories=[], builders_refuses=[], refus_nix=True, permission_contexte=[]))

    def test_hash_et_telechargement_sans_url(self):
        r = m.classer('error: hash mismatch in fixed-output derivation\ncurl: (22) URL-privee\n')
        self.assertEqual(r['categories'], ['hash_refuse', 'telechargement_refuse'])
        self.assertNotIn('privee', json.dumps(r))

    def test_contexte_permission_sans_chemin_ni_contenu(self):
        r = m.classer('compiler.sh: line 4: cd: /root/nom-confidentiel: Permission denied\n')
        self.assertEqual(r['permission_contexte'], ['compilateur_mrjam', 'cd', 'repertoire_root'])
        self.assertNotIn('confidentiel', json.dumps(r))

    def test_nettoyage_ressources_spi_classe_sans_chemin(self):
        r = m.classer("rm: cannot remove '/tmp/confidentiel/classes/META-INF/services/org.keycloak.authentication.AuthenticatorFactory': Permission denied\n")
        self.assertIn('nettoyage_spi_refuse', r['categories'])
        self.assertEqual(r['permission_contexte'], ['rm', 'repertoire_tmp', 'ressources_spi'])
        self.assertNotIn('confidentiel', json.dumps(r))

    def test_journal_public_lien_ou_trop_grand_refuses(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'journal'; p.write_text('error: valeur-secrete'); p.chmod(0o644)
            with self.assertRaises(ValueError): m.lire(p)
            p.chmod(0o600); lien = Path(d) / 'lien'; lien.symlink_to(p)
            with self.assertRaises(OSError): m.lire(lien)
            p.write_bytes(b'a' * 262145)
            with self.assertRaises(ValueError): m.lire(p)


if __name__ == '__main__': unittest.main()
