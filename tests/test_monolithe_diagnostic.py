import importlib.util
from pathlib import Path
import unittest
import json

s=importlib.util.spec_from_file_location('diagnostic',Path(__file__).resolve().parents[1]/'scripts/monolithe-diagnostic.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)


class Diagnostic(unittest.TestCase):
    def test_unit_values_are_never_emitted(self):
        a={'units':{'auth':'ExecStart=ancien\nEnvironment=SECRET=prive-a\nUser=auth'}}
        b={'units':{'auth':'ExecStart=nouveau\nEnvironment=SECRET=prive-b\nUser=auth'}}
        r=m.differences(a,b)
        self.assertEqual(r[0]['proprietes_modifiees'],['Environment','ExecStart'])
        self.assertNotIn('prive',json.dumps(r));self.assertNotIn('ancien',json.dumps(r))

    def test_identical_and_structured_changes(self):
        self.assertEqual(m.differences({'a':1},{'a':1}),[])
        self.assertEqual(m.differences({'postgres':{'package':'a'}},{'postgres':{'package':'b'}})[0]['champ'],'/postgres/package')

    def test_identmap_diagnostic_ne_revele_pas_les_valeurs_inconnues(self):
        a='map_prive compte_prive role_prive\n'
        b=a+'mrjam_metier mrjam-metier vision\n'
        r=m.diagnostic_identmap(a,b)
        self.assertTrue(r['ancien_prefixe_preserve'])
        self.assertEqual(r['positions_ajouts']['vision'],[1])
        self.assertFalse(r['seuls_ajouts_attendus'])
        self.assertNotIn('prive',json.dumps(r))

    def test_identmap_compte_les_champs_et_les_doublons(self):
        r=m.diagnostic_identmap('m u r','m u rmrjam_metier mrjam-metier vision\nmrjam_metier mrjam-metier vision')
        self.assertEqual(r['nombre_colonnes_apres'],[5,3])
        self.assertFalse(r['ancien_prefixe_preserve'])
        self.assertEqual(r['positions_ajouts']['vision'],[1])


if __name__=='__main__':unittest.main()
