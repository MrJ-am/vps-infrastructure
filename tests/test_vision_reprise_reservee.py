"""Preuve exacte exigée et association existante constatée sans modification."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('reservee',ROOT/'scripts/vision-reprise-reservee.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)


class Reprise(unittest.TestCase):
    def test_diagnostic_reel_exact_et_complet_necessaire(self):
        r=json.loads((ROOT/'operations/vision-activation-diagnostic-reel.json').read_text())
        m.verifier_diagnostic(r)
        for k,v in [('version',True),('infrastructure','a'*40),('essai','a'*40),
                ('schema',dict(nombre=18,maximum=18)),('retour_effectif',False),
                ('association_initiale_preservee',False),('identite_courante_retablie',False),
                ('inscriptions',True),('activation',True)]:
            d=copy.deepcopy(r);d[k]=v
            with self.subTest(k=k),self.assertRaises(ValueError):m.verifier_diagnostic(d)

    def test_verification_ne_modifie_pas_l_association(self):
        i=dict(issuer='https://log.mrj.am/realms/mrjam',sujet='synthetique')
        h=dict(utilisateur_historique='synthetique')
        r=dict(comptes=1,administrateurs=1,identites=1,issuer=i['issuer'],sujet=i['sujet'],
            utilisateur=h['utilisateur_historique'],actif=True,inscriptions=False)
        requetes=[]
        def sql(q):
            requetes.append(q);return json.dumps(r) if 'json_build_object' in q else 't'
        m.verifier_association(sql,i,h)
        self.assertTrue(all(q.startswith('SELECT ') for q in requetes))
        for k,v in [('comptes',2),('actif',False),('sujet','autre'),('inscriptions',True)]:
            original=r[k];r[k]=v
            with self.subTest(k=k),self.assertRaises(ValueError):m.verifier_association(sql,i,h)
            r[k]=original


if __name__=='__main__':unittest.main()
