"""Provenance et sélection de la portée interne Audition, sans faux reçu."""
import importlib.util
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import assemblage


class Audition(unittest.TestCase):
    def test_suites_ciblees_et_absence_de_workflow_satellite(self):
        selection = assemblage.selection(['vps/lisp/audition/services.lisp'], assemblage.catalogue())
        self.assertIn('audition-metier', selection)
        self.assertNotIn('logique-interface', selection)
        self.assertFalse(list((ROOT / '.github/workflows').glob('*audition*')))

    def test_style_propage_au_consommateur_interne(self):
        selection = assemblage.selection(['style/src/MrJam/Theme.elm'], assemblage.catalogue())
        self.assertIn('audition-interface', selection)

    def test_graphe_et_verrous_exacts(self):
        m = assemblage.manifeste()
        self.assertEqual(m['composants_internes']['audition']['revision'], 'self')
        edge = m['frontends_infrastructure']['audition']
        self.assertRegex(edge['revision_style'], '^[a-f0-9]{40}$')
        self.assertRegex(edge['revision_signature'], '^[a-f0-9]{40}$')
        self.assertIn('"mrjam-audition"', (ROOT / 'mrjam-metier.asd').read_text())
        self.assertIn('mrjam-audition.asd', (ROOT / 'assemblage/metier.nix').read_text())
        self.assertIn('mrjam-audition.asd', (ROOT / 'assemblage/charger.lisp').read_text())
        self.assertIn('./audition.nix', (ROOT / 'modules/gateway.nix').read_text())

    def test_aucune_dependance_externe_nouvelle(self):
        audition = json.loads((ROOT / 'interface-audition/elm.json').read_text())
        log = json.loads((ROOT / 'interface-log/elm.json').read_text())
        self.assertEqual(audition['dependencies'], log['dependencies'])
        self.assertEqual(audition['test-dependencies'], log['test-dependencies'])
        spec = importlib.util.spec_from_file_location('verifier_dependances', ROOT / 'scripts/verifier-dependances.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        module.verifier()

    def test_promotion_nix_conserve_log_et_les_services_installes(self):
        with tempfile.TemporaryDirectory(prefix='audition-nix-') as temp:
            base = Path(temp) / 'base.nix'
            base.write_text('{ lib, pkgs, ... }: { imports = [ '
                + json.dumps(str(ROOT / 'tests/log-connexion-base.nix'))
                + ' ]; infrastructure.metier.paquet=lib.mkOverride 30 pkgs.coreutils; }')
            expression = 'let pkgs=import <nixpkgs> {}; in import ' + str(ROOT / 'assemblage/audition/evaluation.nix') + ' { '
            expression += 'configuration=' + json.dumps(str(base)) + '; moduleInterface=' + json.dumps(str(ROOT / 'assemblage/audition/module.nix')) + '; '
            expression += 'moduleAudition=builtins.toPath ' + json.dumps(str(ROOT / 'modules/audition.nix')) + '; '
            expression += 'site=builtins.toPath ' + json.dumps(str(ROOT / 'interface-audition/dist')) + '; paquetMetier=pkgs.sbcl; }'
            pkgs = ROOT / ('state/outils-sources/nixpkgs-' + assemblage.manifeste()['toolchain']['production']['nixpkgs_revision'])
            p = subprocess.run(['nix-instantiate', '-I', 'nixpkgs=' + str(pkgs), '--eval', '--strict', '--json', '--expr', expression], capture_output=True, text=True)
        if p.returncode: self.fail('Évaluation Nix refusée : ' + p.stderr[-1200:])
        r = json.loads(p.stdout)
        self.assertTrue(r['invariants'], str((r['differences'], r['unitesDifferentes'])))
        self.assertTrue(r['assertions']); self.assertTrue(r['nativeActif'])
        self.assertNotEqual(r['paquetAvant'], r['paquetApres'])
        self.assertEqual(r['authenticationApres'].replace('local vision audition_app peer map=mrjam_metier\n', ''),
                         r['authenticationAvant'].replace('local vision audition_app peer map=mrjam_metier\n', ''))
        self.assertTrue(r['host']['enableACME']); self.assertTrue(r['host']['forceSSL'])
        self.assertIn('audition_app', r['auditionDsn'])

    def test_retour_code_garde_les_donnees_recentes(self):
        from types import SimpleNamespace
        from unittest.mock import Mock, patch
        spec = importlib.util.spec_from_file_location('promotion_audition', ROOT / 'scripts/audition-promouvoir.py')
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        stage = SimpleNamespace(etat=lambda _: {'generation': 'nouveau'}, commande=Mock())
        plan = {'avant': {'generation': 'ancien', 'configuration_lien': '/fixture/ancien.nix'}, 'candidat': 'nouveau'}
        with patch.object(m, 'configuration') as c, patch.object(m, 'ecrire') as e:
            m.retour(Path('/fixture'), stage, plan)
        c.assert_called_once_with('/fixture/ancien.nix')
        self.assertEqual(stage.commande.call_count, 2)
        self.assertTrue(e.call_args.args[1]['donnees_et_identites_non_restaurees'])
        self.assertFalse(any('restore' in str(a) or 'psql' in str(a) for a in stage.commande.call_args_list))

    def test_retour_refuse_une_bascule_concurrente(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        spec = importlib.util.spec_from_file_location('promotion_audition', ROOT / 'scripts/audition-promouvoir.py')
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        stage = SimpleNamespace(etat=lambda _: {'generation': 'concurrente'}, commande=Mock())
        with self.assertRaises(ValueError):
            m.retour(Path('/fixture'), stage, {'avant': {'generation': 'ancien'}, 'candidat': 'nouveau'})
        stage.commande.assert_not_called()

    def test_unite_transitoire_collectee_et_erreur_reelle_distinctes(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        spec = importlib.util.spec_from_file_location('promotion_audition', ROOT / 'scripts/audition-promouvoir.py')
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        with patch.object(m.subprocess, 'run', return_value=SimpleNamespace(returncode=1, stdout='LoadState=not-found\nActiveState=inactive\nMainPID=0\n')):
            self.assertEqual(m.etat_unite('temoin.service')['LoadState'], 'not-found')
        with patch.object(m.subprocess, 'run', return_value=SimpleNamespace(returncode=1, stdout='')):
            with self.assertRaises(ValueError):m.etat_unite('temoin.service')


if __name__ == '__main__': unittest.main()
