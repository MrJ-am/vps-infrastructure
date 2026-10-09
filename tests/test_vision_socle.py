"""Les résultats du diagnostic système ne publient pas de données privées."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location('socle', Path(__file__).resolve().parents[1] / 'scripts/vision-socle-auditer.py')
SOCLE = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(SOCLE)


class DiagnosticSocle(unittest.TestCase):
    def test_configuration_privee_absente_du_rapport(self):
        c = {'systeme': SOCLE.ATTENDU, 'postgres_majeure': '17',
            'postgres_tcp': False, 'postgres_ecoute': '',
            'recipient_age': 'prive', 'mot_de_passe': 'secret-personnel'}
        r = SOCLE.resume(c, SOCLE.ATTENDU)
        self.assertEqual(set(r), {'evaluation_reussie', 'generation',
            'generation_identique', 'postgres_17', 'postgres_sans_tcp', 'postgres_ecoute_vide'})
        self.assertNotIn('secret-personnel', str(r))

    def test_divergences_identifiees_separement(self):
        r = SOCLE.resume({'systeme': SOCLE.ATTENDU, 'postgres_majeure': '16',
            'postgres_tcp': True, 'postgres_ecoute': 'adresse-non-publiee'},
            SOCLE.ATTENDU.replace('y1azkcag', 'aaaaaaaa'))
        for cle in ('generation_identique', 'postgres_17', 'postgres_sans_tcp', 'postgres_ecoute_vide'):
            self.assertFalse(r[cle])
        self.assertNotIn('adresse-non-publiee', str(r))

    def test_chemin_arbitraire_non_publie(self):
        with self.assertRaisesRegex(ValueError, '^Métadonnée de génération inattendue$'):
            SOCLE.generation('/home/personne/contenu-prive')

    def test_comparaison_refuse_une_source_hors_store_sans_la_lire(self):
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('Lecture privée interdite')):
            r = SOCLE.comparer_sources('/home/personne/prive', '/home/personne/autre')
        self.assertEqual(r, {'sources_identifiees': False})

    def test_script_manquant_reste_un_resultat_explicite(self):
        a = '/nix/store/' + 'a' * 32 + '-vision-fournisseur-c0bfcac'
        b = '/nix/store/' + 'b' * 32 + '-vision-fournisseur-c0bfcac'
        with patch.object(Path, 'is_file', return_value=False), patch.object(Path, 'is_dir', return_value=False), patch.object(Path, 'read_bytes', side_effect=AssertionError('Aucun contenu à lire')):
            r = SOCLE.comparer_sources(a, b)
        self.assertTrue(r['sources_identifiees'])
        self.assertFalse(r['deux_scripts_identiques'])
        self.assertFalse(r['arborescence_identique'])
        self.assertEqual(r['scripts_presents']['scripts/backfill_embeddings.py'], {'actif': False, 'calcule': False})


if __name__ == '__main__': unittest.main()
