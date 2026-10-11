import importlib.util
from pathlib import Path
import unittest
spec=importlib.util.spec_from_file_location('impact',Path(__file__).resolve().parents[1]/'scripts/ci-infrastructure-impact.py')
impact=importlib.util.module_from_spec(spec);spec.loader.exec_module(impact)


class SuitesExploitation(unittest.TestCase):
    def test_routage_metier_requalifie_nix_sans_retester_un_idp_inchange(self):
        r=impact.selection(['modules/metier.nix','apps/matheval.nix'])
        self.assertTrue(r['check']);self.assertFalse(r['keycloak']);self.assertFalse(r['migration-vision'])
    def test_plugin_et_adaptateur_identite_invalident_idp_reel(self):
        for p in ['services/keycloak-mrjam/src/org/mrjam/identite/FermerCompte.java','services/mrj-auth/oidc.py','modules/identite.nix']:
            r=impact.selection([p]);self.assertTrue(r['keycloak']);self.assertTrue(r['keycloak-unix-optimise'])
    def test_migration_sql_et_outil_de_retour_invalident_le_retour(self):
        for p in ['modules/postgresql.nix','scripts/vision-retour-executer.py','tests/test_migration.py']:
            self.assertTrue(impact.selection([p])['migration-vision'])
    def test_toolchain_et_reference_requalifient_tout(self):
        self.assertTrue(all(impact.selection(['tests/nixpkgs.json']).values()))
        self.assertTrue(all(impact.selection([],reference=True).values()))


if __name__=='__main__':unittest.main()
