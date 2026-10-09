"""La construction exige une preuve réelle complète du même candidat."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('construction', ROOT / 'scripts/vision-identite-construire.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


class Preuve(unittest.TestCase):
    def setUp(self):
        self.preuve = json.loads((ROOT / 'operations/vision-multiutilisateur-qualification.json').read_text())
        self.candidat = json.loads((ROOT / 'operations/vision-multiutilisateur-candidat.json').read_text())
        self.rapport = {k: self.preuve[k] for k in ('version', 'infrastructure', 'vision', 'style',
            'restauration_vision_reelle', 'migrations_sans_perte', 'retour_acl_owners_rls',
            'retour_rejouable', 'activation', 'inscriptions')}

    def test_preuve_complete_acceptee(self):
        m.preuve_preparation(self.rapport, self.preuve, self.candidat)

    def test_preuve_partielle_ou_activee_refusee(self):
        for k in ('restauration_vision_reelle', 'migrations_sans_perte', 'retour_acl_owners_rls',
                'retour_rejouable', 'activation', 'inscriptions'):
            with self.subTest(k=k), self.assertRaises(m.ConstructionRefusee):
                r = {**self.rapport, k: not self.rapport[k]}
                m.preuve_preparation(r, self.preuve, self.candidat)

    def test_autre_preparation_ou_autre_candidat_refuse(self):
        with self.assertRaises(m.ConstructionRefusee):
            m.preuve_preparation({**self.rapport, 'infrastructure': 'f' * 40}, self.preuve, self.candidat)
        for k in ('vision', 'style', 'source_sha256'):
            with self.subTest(k=k), self.assertRaises(m.ConstructionRefusee):
                c = copy.deepcopy(self.candidat); c[k] = 'f' * len(c[k])
                m.preuve_preparation(self.rapport, self.preuve, c)


if __name__ == '__main__': unittest.main()
