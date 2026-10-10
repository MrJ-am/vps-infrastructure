"""Refuser une source différente plutôt que réécrire arbitrairement NixOS."""
import hashlib
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
s = importlib.util.spec_from_file_location('entree_configuration_test',ROOT/'scripts/vision-entree-configuration.py')
m = importlib.util.module_from_spec(s); s.loader.exec_module(m)


class Entree(unittest.TestCase):
    def setUp(self):
        self.essai = Path('/root/vision-identite-amorcage-essais')/('a'*40)
        self.module = '/root/source/modules/identite-amorcage.nix'
        self.fournisseur = '/nix/store/'+'a'*32+'-fournisseur'
        self.sauvegarde = '{ imports = [ /etc/nixos/source/configuration.nix ]; }\n'
        self.empreinte = hashlib.sha256(self.sauvegarde.encode()).hexdigest()
        self.ancien = m.entree(m.COURANTE,self.module,self.fournisseur)

    def test_fichier_regulier_copie_stable_et_symlink_existant_preserve(self):
        copie = self.essai/'configuration-avant.nix'
        self.assertEqual(m.reference_originale(m.COURANTE,copie),copie)
        self.assertEqual(m.reference_originale('/root/ancienne/entree.nix',copie),Path('/root/ancienne/entree.nix'))
        with self.assertRaises(ValueError): m.reference_originale(m.COURANTE,m.COURANTE)

    def test_cycle_exact_repare_et_entree_deja_identique_requalifiable(self):
        nouveau = m.reparer(self.ancien,self.sauvegarde,self.empreinte,self.essai,self.module,self.fournisseur)
        self.assertNotIn('"/etc/nixos/configuration.nix"',nouveau)
        self.assertIn(str(self.essai/'configuration-avant.nix'),nouveau)
        self.assertEqual(m.reparer(nouveau,self.sauvegarde,self.empreinte,self.essai,self.module,self.fournisseur),nouveau)

    def test_copie_modifiee_et_source_etrangere_refusees(self):
        with self.assertRaises(ValueError): m.reparer(self.ancien,self.sauvegarde+'# modifie',self.empreinte,self.essai,self.module,self.fournisseur)
        for ancien in (self.ancien+'# ajout',self.ancien.replace('enable = true','enable = false'),self.ancien.replace('configuration.nix','autre.nix')):
            with self.subTest(ancien=ancien), self.assertRaises(ValueError):
                m.reparer(ancien,self.sauvegarde,self.empreinte,self.essai,self.module,self.fournisseur)

    def test_injection_de_chemin_ou_fournisseur_refusee(self):
        for path in ('relative.nix','/root/module";.nix','/root/fichier.secret'):
            with self.assertRaises(ValueError): m.entree(path,self.module,self.fournisseur)
        with self.assertRaises(ValueError): m.entree(m.COURANTE,self.module,self.fournisseur+'"; abort "secret')


if __name__ == '__main__': unittest.main()
