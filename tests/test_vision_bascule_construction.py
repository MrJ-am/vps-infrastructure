"""La classification d'une construction n'expose aucun chemin ou texte libre."""
import importlib.util
import json
from pathlib import Path
import unittest

s = importlib.util.spec_from_file_location('construction_bascule',Path(__file__).resolve().parents[1]/'scripts/vision-bascule-construction-diagnostiquer.py')
m = importlib.util.module_from_spec(s); s.loader.exec_module(m)


class Projection(unittest.TestCase):
    def test_source_privee_non_exportee(self):
        texte = 'do not know how to unpack source archive /root/vision-bascule-preparations/'+('a'*40)+'/vision\nsecret@example.test\n'
        r = m.classer(texte)
        self.assertEqual(r['categories'],['archive_non_reconnue','copie_source_hors_store'])
        self.assertNotIn('/root/',json.dumps(r)); self.assertNotIn('example',json.dumps(r))

    def test_composants_echoues_connus_uniquement(self):
        texte = "error: builder for '/nix/store/"+('a'*32)+"-vision-bootstrap-1.3.0.drv' failed with exit code 1;\n"
        texte += "error: builder for '/nix/store/"+('b'*32)+"-contenu-confidentiel.drv' failed\n"
        self.assertEqual(m.classer(texte)['composants'],['vision-bootstrap'])
        self.assertNotIn('confidentiel',json.dumps(m.classer(texte)))

    def test_autres_causes_fermees(self):
        r = m.classer('No space left on device\nHTTP error 403\nCOMPILE-FILE-ERROR\nsecret')
        self.assertEqual(r['categories'],['disque_plein','lisp_compilation','reseau'])
        self.assertEqual(m.classer('texte privé'),dict(categories=[],composants=[]))


if __name__ == '__main__': unittest.main()
