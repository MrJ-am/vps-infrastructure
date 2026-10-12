"""Un échec distant est diagnostiqué une fois, sans répétition de ses effets."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
s=importlib.util.spec_from_file_location('operation_monolithe',ROOT/'scripts/monolithe-operation.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)


class Operation(unittest.TestCase):
    def test_echec_restauration_empeche_activation_et_rejeu(self):
        e=subprocess.CalledProcessError(1,['operation-fermee'])
        with patch.dict(os.environ,{'GITHUB_ACTIONS':'true','GITHUB_REF':'refs/heads/main','MRJAM_OPERATION':'deployer'}),\
             patch.object(m.stage,'descriptor',return_value={'revision_operateurs':'a'*40}),\
             patch.object(m.stage,'manifeste',return_value={'toolchain':{'production':{'nixpkgs':'/nix/source'}}}),\
             patch.object(m.stage,'ssh',side_effect=e) as ssh,patch.object(m,'diagnostiquer') as diag:
            with self.assertRaises(subprocess.CalledProcessError) as erreur:m.main()
            self.assertIs(erreur.exception,e);self.assertEqual(ssh.call_count,1)
            self.assertIn('monolithe-restaurer.py',ssh.call_args.args[0])
            diag.assert_called_once_with('/nix/source','a'*40)

    def test_diagnostic_indisponible_ne_masque_pas_erreur_initiale(self):
        e=subprocess.CalledProcessError(1,['operation-fermee'])
        with patch.dict(os.environ,{'GITHUB_ACTIONS':'true','GITHUB_REF':'refs/heads/main','MRJAM_OPERATION':'retour'}),\
             patch.object(m.stage,'descriptor',return_value={'revision_operateurs':'a'*40}),\
             patch.object(m.stage,'manifeste',return_value={'toolchain':{'production':{'nixpkgs':'/nix/source'}}}),\
             patch.object(m.stage,'ssh',side_effect=e) as ssh,\
             patch.object(m,'diagnostiquer',side_effect=ValueError('valeur-privee')),patch.object(m.sys,'stderr') as stderr:
            with self.assertRaises(subprocess.CalledProcessError) as erreur:m.main()
            self.assertIs(erreur.exception,e);self.assertEqual(ssh.call_count,1)
            self.assertNotIn('valeur-privee',''.join(str(c) for c in stderr.write.call_args_list))


if __name__=='__main__':unittest.main()
