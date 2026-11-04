"""Fresh process regression: recipe templates must not shadow installed trust."""
import os
from pathlib import Path
import subprocess
import sys
import unittest


class TrustImport(unittest.TestCase):
    def test_unexpanded_recipe_control_cannot_replace_installed_anchor(self):
        path = Path(__file__).resolve().parent / 'delivery_preparation_service.py'
        code = '''
import importlib.util,pathlib,sys
p=pathlib.Path(sys.argv[1])
s=importlib.util.spec_from_file_location('isolated_preparation_import',p)
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
a=m.D.A
assert a.__file__.startswith('/nix/store/ixhqrvgq1vixg0g0fc01lwkdprxxkmn7-mrjam-validation-admission-control-1/lib/')
assert pathlib.Path(a.ANCHOR_PATH).is_file()
assert '@' not in a.ANCHOR_PATH
assert m.A.A is a
'''
        result = subprocess.run([sys.executable, '-I', '-S', '-c', code, str(path)],
            env={**os.environ, 'MRJAM_DELIVERY_RECIPE': str(path.parents[3]),
                 'MRJAM_DELIVERY_NIX': '/unused-by-import'},
            capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr.decode())


if __name__ == '__main__': unittest.main()
