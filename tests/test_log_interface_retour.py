import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
s=importlib.util.spec_from_file_location('operation_retour',ROOT/'scripts/log-operation.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)


class Retour(unittest.TestCase):
    def test_retour_presentation_ferme_sans_bascule_idp(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'operations').mkdir()
            (root/'operations/log-interface-candidat.json').write_text(json.dumps({'revision_sources':'a'*40}))
            with patch.object(m,'ROOT',root),patch.dict(os.environ,{'GITHUB_ACTIONS':'true','GITHUB_REF':'refs/heads/main','MRJAM_OPERATION':'interface-retour'}),\
                 patch.object(m.stage,'ssh') as ssh,patch.object(m.stage,'main') as staging,\
                 patch.object(m.stage,'manifeste',return_value={'toolchain':{'production':{'nixpkgs':'/fixture'}}}):
                m.main();staging.assert_not_called()
                code=ssh.call_args.kwargs['input'].decode()
                self.assertIn('m.retour(d,m.charger_stage(p),p)',code)
                self.assertNotIn('log-activer.py',code)
                self.assertNotIn('recover-account',code)
                self.assertNotIn('pg_restore',code)
    def test_revision_arbitraire_refusee_avant_ssh(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'operations').mkdir()
            (root/'operations/log-interface-candidat.json').write_text(json.dumps({'revision_sources':'../../autre'}))
            with patch.object(m,'ROOT',root),patch.dict(os.environ,{'GITHUB_ACTIONS':'true','GITHUB_REF':'refs/heads/main','MRJAM_OPERATION':'interface-retour'}),patch.object(m.stage,'ssh') as ssh:
                with self.assertRaises(ValueError):m.main()
                ssh.assert_not_called()


if __name__=='__main__':unittest.main()
