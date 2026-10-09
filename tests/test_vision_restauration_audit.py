"""Le diagnostic privé classe les refus sans reproduire aucune donnée."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('restauration', Path(__file__).resolve().parents[1] / 'scripts/vision-restauration-auditer.py')
MODULE = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(MODULE)


class Diagnostic(unittest.TestCase):
    def test_erreur_role_reste_anonyme(self):
        texte = 'pg_restore: error: could not execute query: ERROR:  role "personne-privee" does not exist\nCommand was: contenu personnel\n'
        resultat = MODULE.classer(texte)
        self.assertEqual(resultat['categories'], ['role_absent'])
        self.assertTrue(resultat['refus_pg_restore'])
        self.assertNotIn('personne-privee', json.dumps(resultat))
        self.assertNotIn('personnel', json.dumps(resultat))

    def test_psql_et_categories_distinctes(self):
        resultat = MODULE.classer('psql:<stdin>:4: ERROR:  CREATE DATABASE cannot run inside a transaction block\n')
        self.assertEqual(resultat['categories'], ['creation_base_en_transaction'])
        self.assertTrue(resultat['refus_psql'])
        self.assertFalse(resultat['refus_pg_restore'])

    def test_un_texte_arbitraire_ne_devient_pas_une_erreur(self):
        resultat = MODULE.classer('Note personnelle : role absent, Permission denied, extension vector\n')
        self.assertEqual(resultat['categories'], [])
        self.assertFalse(resultat['refus_psql'])
        self.assertFalse(resultat['refus_pg_restore'])

    def test_erreur_sql_technique_sans_valeur_privee(self):
        texte = 'pg_restore: error: could not execute query: ERROR:  collation "nom-prive" for encoding "SQL_ASCII" does not exist\n'
        resultat = MODULE.classer(texte)
        self.assertEqual(resultat['categories'], ['collation_absente'])
        self.assertTrue(resultat['refus_sql'])
        self.assertTrue(resultat['encodage_sql_ascii_mentionne'])
        self.assertNotIn('nom-prive', json.dumps(resultat))

    def test_refus_inconnu_ne_restitue_pas_son_texte(self):
        texte = 'pg_restore: error: could not execute query: ERROR:  refus inconnu avec du contenu personnel\n'
        resultat = MODULE.classer(texte)
        self.assertEqual(resultat['categories'], [])
        self.assertTrue(resultat['refus_sql'])
        self.assertNotIn('personnel', json.dumps(resultat))

    def test_copie_unicode_sans_restituer_la_table(self):
        texte = 'pg_restore: error: COPY failed for table "prive-synthetique": ERROR:  unsupported Unicode escape sequence\nDETAIL: contenu personnel\n'
        resultat = MODULE.classer(texte)
        self.assertEqual(resultat['categories'], ['echappement_unicode_non_supporte'])
        self.assertTrue(resultat['refus_copy'])
        self.assertNotIn('synthetique', json.dumps(resultat))
        self.assertNotIn('personnel', json.dumps(resultat))

    def test_refus_de_longueur_sans_restituer_la_ligne(self):
        texte = 'pg_restore: error: COPY failed for table "vision_fiches": ERROR:  new row for relation "vision_fiches" violates check constraint "vision_fiches_titre_check"\nDETAIL: Failing row contains (contenu privé synthétique).\n'
        resultat = MODULE.classer(texte)
        self.assertEqual(resultat['categories'], ['ligne_refusee_contrainte'])
        self.assertTrue(resultat['longueur_titre_fiche_refusee'])
        self.assertNotIn('contenu privé', json.dumps(resultat))

    def test_lecture_refuse_lien_permissions_et_depassement(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'journal'; p.write_text('privé'); p.chmod(0o600)
            self.assertEqual(MODULE.lire(p), 'privé')
            lien = Path(d) / 'lien'; lien.symlink_to(p)
            with self.assertRaises(OSError): MODULE.lire(lien)
            p.chmod(0o644)
            with self.assertRaises(ValueError): MODULE.lire(p)
            p.chmod(0o600); p.write_bytes(b'x' * 262145)
            with self.assertRaises(ValueError): MODULE.lire(p)


if __name__ == '__main__': unittest.main()
