import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('assemblage', Path(__file__).resolve().parents[1] / 'scripts/assemblage.py')
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


class Selection(unittest.TestCase):
    def setUp(self):
        self.c = a.catalogue()

    def test_local_ne_declenche_pas_tous_les_consommateurs(self):
        s = a.selection(['matheval/lisp/statistiques.lisp'], self.c)
        self.assertIn('matheval-pures', s)
        self.assertNotIn('logique-correcteur', s)

    def test_macro_ou_json_communs_invalident_les_consommateurs(self):
        s = a.selection(['vision/src/json.lisp'], self.c)
        self.assertIn('matheval-pures', s)
        self.assertIn('vision-contrats', s)

    def test_sql_invalide_integration_et_migration(self):
        s = a.selection(['vision/migrations/019_multiutilisateur.sql'], self.c)
        self.assertIn('vision-postgresql', s)
        self.assertIn('integration-securite', s)
        self.assertIn('migration', s)

    def test_style_invalide_tous_les_frontends(self):
        s = a.selection(['style/src/MrJam/Composants.elm'], self.c)
        for n in ('vision-interface', 'matheval-interface', 'logique-interface'):
            self.assertIn(n, s)

    def test_authentification_invalide_mcp_et_securite(self):
        s = a.selection(['vps/services/mrj-auth/oidc.py'], self.c)
        self.assertIn('integration-securite', s)
        self.assertIn('navigateur-mcp', s)

    def test_documentation_seule(self):
        self.assertEqual(['editorial'], a.selection(['vps/docs/ETAT.md'], self.c))
        self.assertEqual(['editorial'], a.selection(['matheval/research/memoire.org'], self.c))

    def test_chemin_inconnu_elargit(self):
        self.assertEqual(sorted(self.c), a.selection(['vision/nouveau-generateur.bin'], self.c))

    def test_selection_et_definition_sont_des_entrees(self):
        s = a.selection(['vps/scripts/assemblage.py'], self.c)
        self.assertIn('selection', s)


class Recus(unittest.TestCase):
    def test_aucun_fichier_ok_ne_vaut_recu(self):
        self.assertFalse(a.reutilisable({}, {'a': 1}))

    def test_resultat_environment_et_code_doivent_correspondre(self):
        i = {'entrees': {'x': 'a'}, 'environnement': {'outil': '1'}}
        r = {'format': 1, 'resultat': 'succes', 'identite': i, 'confiance': 'locale-non-attestee'}
        self.assertTrue(a.reutilisable(r, i))
        change = copy.deepcopy(i)
        change['environnement']['outil'] = '2'
        self.assertFalse(a.reutilisable(r, change))
        r['resultat'] = 'echec'
        self.assertFalse(a.reutilisable(r, i))

    def test_aucun_secret_dans_la_configuration_du_recu(self):
        with self.assertRaises(ValueError):
            a.environnement({'configuration': ['OIDC_CLIENT_SECRET']})

    def test_entre_absente_et_lien_externe_refuses(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t)
            with self.assertRaises(ValueError):
                a.entrees({'entrees': {'vps': ['absent']}}, {'vps': p})
            (p / 'externe').symlink_to('/etc/os-release')
            with self.assertRaises(ValueError):
                a.entrees({'entrees': {'vps': ['externe']}}, {'vps': p})
