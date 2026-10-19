"""Vraies évaluations Nix, régression SBCL et refus des bascules hors périmètre."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import test_vision_mcp_configuration as configuration

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'assemblage/vision-mcp-configuration'
spec = importlib.util.spec_from_file_location('promotion', SOURCE/'promote.py')
promotion = importlib.util.module_from_spec(spec); spec.loader.exec_module(promotion)


class PromotionMcp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='vision-mcp-promotion-')
        cls.directory = Path(cls.temp.name)
        # Retirer seulement l'ajout c3adad9 pour rejouer la configuration fautive.
        metier = (ROOT/'modules/metier.nix').read_text()
        line = '          VISION_PUBLIC_MCP_URL = "https://${config.services.vision.domain}/mcp";\n'
        assert metier.count(line) == 1
        (cls.directory/'old-metier.nix').write_text(metier.replace(line, ''))
        cls.base = cls.directory/'base.nix'
        cls.base.write_text('{ imports = [ '+str(ROOT/'tests/log-evaluation-base.nix')+' ./old-metier.nix ]; disabledModules = [ '+json.dumps(str(ROOT/'modules/metier.nix'))+' ]; }')

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def nix(self, expression):
        return json.loads(subprocess.check_output(['nix-instantiate', '--eval', '--strict', '--json',
                                                  '--expr', expression], text=True, stderr=subprocess.PIPE))

    def evaluate(self, correction):
        return self.nix('import '+str(SOURCE/'evaluation.nix')+' { configuration='+json.dumps(str(self.base))+'; correction='+json.dumps(str(correction))+'; }')

    def test_module_promu_corrige_le_vrai_tutoriel_et_uniquement_son_environnement(self):
        result = self.evaluate(SOURCE/'module.nix')
        target = dict(generation=result['before'], url='https://vision.mrj.am/mcp')
        promotion.verify_evaluation(result, target)
        self.assertNotEqual(result['before'], result['after'])
        environment = self.nix('(import <nixpkgs/nixos/lib/eval-config.nix> { system="x86_64-linux"; modules=['+str(self.base)+' '+str(SOURCE/'module.nix')+']; }).config.systemd.services.mrjam-metier.environment')
        configuration.ConfigurationMcp().verifier_tutoriel(environment)
        environment.pop('VISION_PUBLIC_MCP_URL')
        with self.assertRaises(AssertionError):
            configuration.ConfigurationMcp().verifier_tutoriel(environment)

    def test_refuse_une_modification_nextcloud_ou_du_pare_feu(self):
        for extra in ['systemd.services.phpfpm-nextcloud.environment.VISION_TEST="interdit";',
                      'networking.firewall.allowedTCPPorts=[49999];']:
            with self.subTest(extra=extra):
                correction = self.directory/'bad.nix'
                correction.write_text('{ imports=['+str(SOURCE/'module.nix')+']; '+extra+' }')
                result = self.evaluate(correction)
                with self.assertRaisesRegex(ValueError, 'hors périmètre'):
                    promotion.verify_evaluation(result, dict(generation=result['before'], url='https://vision.mrj.am/mcp'))

    def test_refuse_une_adresse_absente_ou_un_changement_de_reference(self):
        result = self.evaluate(SOURCE/'module.nix')
        with self.assertRaisesRegex(ValueError, 'référence'):
            promotion.verify_evaluation(result, dict(generation='autre', url='https://vision.mrj.am/mcp'))
        with self.assertRaisesRegex(ValueError, 'Adresse'):
            promotion.verify_evaluation(result, dict(generation=result['before'], url='https://autre.example/mcp'))

    def test_retour_refuse_ecrasement_configuration_concurrente(self):
        entry = self.directory/'entry.nix'; entry.write_text('configuration concurrente')
        (self.directory/'prepared.json').write_text(json.dumps(dict(base='base', generation='candidate')))
        with patch.object(promotion, 'D', self.directory, create=True), patch.object(promotion, 'ENTRY', entry), \
             patch.object(promotion, 'current', return_value='candidate'), patch.object(promotion, 'boot', return_value='candidate'), \
             patch.object(promotion, 'run') as command:
            with self.assertRaisesRegex(ValueError, 'concurrente'):
                promotion.rollback()
            command.assert_not_called()
        self.assertEqual(entry.read_text(), 'configuration concurrente')

    def test_timer_accepte_unite_collectee_mais_refuse_erreur_systemd(self):
        completed = subprocess.CompletedProcess([], 4, 'LoadState=not-found\nMainPID=0\n', '')
        with patch.object(promotion.subprocess, 'run', return_value=completed), patch.object(promotion, 'run') as command:
            promotion.stop_if_loaded('temoin.service')
            command.assert_not_called()
        completed = subprocess.CompletedProcess([], 1, '', 'erreur système')
        with patch.object(promotion.subprocess, 'run', return_value=completed):
            with self.assertRaisesRegex(ValueError, 'indisponible'):
                promotion.stop_if_loaded('temoin.service')


if __name__ == '__main__':
    unittest.main()
