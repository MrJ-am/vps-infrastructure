"""Une qualification ne doit jamais reconstruire le candidat Nix promu."""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'scripts'))
spec=importlib.util.spec_from_file_location('qualifier_metier',root/'scripts/qualifier-metier.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CandidatNix(unittest.TestCase):
    def test_commande_ordinaire_exerce_le_candidat_sans_reconstruction(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'metier'
            p.write_bytes(b'image deja qualifiee')
            preparation=p.with_suffix('.construction-nix.json')
            preparation.write_text('{}')
            with patch.dict(os.environ,{'MRJAM_TEST_EXECUTABLE':str(p)},clear=True), \
                 patch.object(module,'qualifier_existant') as existant, \
                 patch.object(module,'qualifier') as reconstruire:
                module.main(['--sans-cache'])
                existant.assert_called_once_with(str(p),str(preparation))
                reconstruire.assert_not_called()
            self.assertEqual(p.read_bytes(),b'image deja qualifiee')

    def test_appel_direct_refuse_decraser_le_candidat(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'metier'
            p.write_bytes(b'image deja qualifiee')
            p.with_suffix('.construction-nix.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'sans reconstruction'), \
                 patch.object(module.subprocess,'run') as run:
                module.qualifier(p,True)
            run.assert_not_called()
            self.assertEqual(p.read_bytes(),b'image deja qualifiee')
