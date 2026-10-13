import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('promotion_ui',ROOT/'scripts/log-interface-promouvoir.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)


class Promotion(unittest.TestCase):
    def test_retour_ne_touche_pas_aux_bases_ou_identites(self):
        stage=SimpleNamespace(etat=lambda _:dict(generation='nouveau'),commande=Mock())
        plan=dict(avant=dict(generation='ancien',configuration_lien='/fixture/ancien.nix'),candidat='nouveau')
        with patch.object(m,'configuration') as c,patch.object(m,'ecrire') as e:
            m.retour(Path('/fixture'),stage,plan)
        c.assert_called_once_with('/fixture/ancien.nix')
        self.assertEqual(stage.commande.call_count,2)
        self.assertTrue(e.call_args.args[1]['donnees_et_identites_non_restaurees'])
    def test_retour_refuse_generation_concurrente(self):
        stage=SimpleNamespace(etat=lambda _:dict(generation='concurrente'),commande=Mock())
        with self.assertRaises(ValueError):m.retour(Path('/fixture'),stage,dict(avant=dict(generation='ancien'),candidat='nouveau'))
        stage.commande.assert_not_called()
    def test_module_nix_preserve_tiers_et_native(self):
        sys.path.insert(0,str(ROOT/'scripts'))
        from assemblage import manifeste
        pkgs=str(ROOT/'state/outils-sources'/('nixpkgs-'+manifeste()['toolchain']['production']['nixpkgs_revision']))
        expression='let pkgs=import <nixpkgs> {}; in import '+str(ROOT/'assemblage/log-interface/evaluation.nix')+' { configuration='+json.dumps(str(ROOT/'tests/log-connexion-base.nix'))+'; moduleInterface='+json.dumps(str(ROOT/'assemblage/log-interface/module.nix'))+'; site=builtins.toPath '+json.dumps(str(ROOT/'interface-log/dist'))+'; paquetMetier=pkgs.sbcl; }'
        p=subprocess.run(['nix-instantiate','-I','nixpkgs='+pkgs,'--eval','--strict','--json','--expr',expression],capture_output=True,text=True)
        if p.returncode:raise AssertionError('Évaluation locale Nix refusée : '+p.stderr[-800:])
        r=json.loads(p.stdout)
        self.assertTrue(r['invariants']);self.assertTrue(r['assertions']);self.assertTrue(r['nativeActif'])
        self.assertIn('= /presentation/api',r['locationsApres'])
        self.assertIn('^~ /v1/raw/',r['locationsApres'])
        self.assertNotEqual(r['exeApres'],r['exeAvant'])


if __name__=='__main__':unittest.main()
