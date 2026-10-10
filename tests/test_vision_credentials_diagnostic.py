import importlib.util
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('credentials_diagnostic',ROOT/'scripts/vision-activation-diagnostiquer.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)


class CredentialsDiagnostic(unittest.TestCase):
    def test_categories_fermees_sans_valeur_du_journal(self):
        for erreur,categorie in [('PermissionError: contenu privé', 'permission_refusee'),
                ('FileNotFoundError: secret jamais affiché','fichier_absent'),
                ('Fichier de secret non privé : secret','credential_non_prive'),
                ('Unknown assignment: valeur privée','propriete_systemd_refusee'),
                ('Failed to load credentials: contenu privé','chargement_credentials_refuse'),
                ('AssertionError: privé','assertion_refusee')]:
            with self.subTest(categorie=categorie):
                r=m.projeter_credentials(erreur)
                self.assertIs(r[categorie],True)
                self.assertTrue(all(type(v) is bool for v in r.values()))
                self.assertNotIn('privé',json.dumps(r))
                self.assertNotIn('secret',json.dumps(r).replace('smtp_format_secret_refuse',''))

    def test_erreur_inconnue_ne_restitue_pas_la_valeur(self):
        r=m.projeter_credentials('Informations personnelles et données secrètes inconnues')
        self.assertFalse(any(r.values()))

    def test_seule_ligne_du_programme_public_restituee(self):
        t='File "<string>", line 5, in <module>\nFile "/root/secret", line 9\nFile "<string>", line 40'
        self.assertEqual(m.lignes_python_credentials(t),[5])


if __name__=='__main__':unittest.main()
