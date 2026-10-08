"""Les pièces externes restent compatibles et les fermetures exigent l'IdP isolé."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('registre_rejouer',Path(__file__).resolve().parents[1]/'scripts/vision-effacements-rejouer.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class Registre(unittest.TestCase):
    def test_compatibilite_pieces_v1_et_v2_et_refus_avant_mutation(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'registre';commun={'version':2,'type':'fermeture_commune','emetteur':m.EMETTEUR,
                'sujet':'sujet','confirmee_a':123,'outils':{'vision':['personne']}}
            p.write_text('\n'.join(json.dumps(v) for v in [
                {'utilisateur':'personne','confirmee_a':123},{'version':1,'utilisateur':'personne','confirmee_a':123},commun]))
            self.assertEqual(m.charger([p]),({'personne'},{'sujet'}))
            with patch.object(m.subprocess,'run') as sql:
                with self.assertRaisesRegex(ValueError,'fournisseur restauré isolé'):m.rejouer(p,'vision_restauration_test')
                sql.assert_not_called()
            for faux in ({**commun,'emetteur':'https://etranger.test'},
                         {**commun,'outils':{'vision':["personne';DROP"]}},
                         {**commun,'confirmee_a':True},{**commun,'courriel':'tiers@example.test'}):
                p.write_text(json.dumps(faux))
                with self.assertRaises(ValueError):m.charger([p])
    def test_cible_active_ou_distante_refusee(self):
        with self.assertRaises(ValueError):m.rejouer([],'vision')
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'prive';p.write_text(json.dumps({'version':1,'base_isolee':'http://127.0.0.1:8085',
                'realm':'mrjam','utilisateur':'synthetique','mot_de_passe':'synthetique'}));p.chmod(0o600)
            with self.assertRaisesRegex(ValueError,'Fournisseur isolé'):m.effacer_identites({'sujet'},p)


if __name__=='__main__':unittest.main()
