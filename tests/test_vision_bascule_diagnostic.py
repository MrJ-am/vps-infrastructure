"""Les détails privés d'une exception ne traversent jamais la projection."""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
s = importlib.util.spec_from_file_location('bascule_diagnostic',ROOT/'scripts/vision-bascule-diagnostiquer.py')
m = importlib.util.module_from_spec(s); s.loader.exec_module(m)


class Diagnostic(unittest.TestCase):
    def test_cadre_prouve_et_classe_sans_message_prive(self):
        source = 'def preparer():\n    raise ValueError("texte confidentiel")\n'
        trace = '  File "'+str(m.DOSSIER/'source/scripts/vision-bascule-preparer.py')+'", line 2, in preparer\nValueError: secret@example.test contenu confidentiel\n'
        r = m.classer(trace,{'vision-bascule-preparer.py':source})
        self.assertEqual(r['cadres'],[dict(fichier='vision-bascule-preparer.py',ligne=2,fonction='preparer')])
        self.assertEqual(r['exceptions'],['ValueError'])
        self.assertNotIn('confidentiel',json.dumps(r)); self.assertNotIn('example.test',json.dumps(r))

    def test_fichier_fonction_ligne_et_revision_etrangers_omis(self):
        base = str(m.DOSSIER/'source/scripts')+'/'
        source = 'def preparer():\n    return 1\n'
        for path,n,f in ((base+'prive.py',2,'preparer'),(base+'vision-bascule-preparer.py',99,'preparer'),
                         (base+'vision-bascule-preparer.py',2,'secret'),('/root/autre/vision-bascule-preparer.py',2,'preparer')):
            trace = '  File "'+path+'", line '+str(n)+', in '+f+'\n'
            self.assertEqual(m.classer(trace,{'vision-bascule-preparer.py':source})['cadres'],[])

    def test_categories_fermees_pas_de_message_libre(self):
        r = m.classer('ValueError: Archive trop grande\nSECRET: adresse et texte\n',{})
        self.assertEqual(r,dict(cadres=[],exceptions=['ValueError'],categories=['archive_taille']))
        self.assertEqual(m.classer('  raise ValueError("Archive trop grande")\n',{})['categories'],[])

    def test_invariants_distinguent_generation_et_paquet(self):
        c = dict(systeme='generation-a',postgres_paquet='paquet-pg',postgres_majeure='17',postgres_tcp=False,postgres_ecoute='',fournisseur_source='provider')
        a = dict(systeme_amorcage='generation-a'); r = dict(postgres_paquet='paquet-pg')
        candidat = dict(audit=dict(fournisseur='provider'))
        self.assertTrue(all(m.invariants(c,a,r,candidat).values()))
        autre = m.invariants({**c,'systeme':'generation-b'},a,r,candidat)
        self.assertFalse(autre['generation_identique']); self.assertTrue(autre['paquet_postgresql_identique'])
        self.assertFalse(m.invariants({**c,'postgres_tcp':1},a,r,candidat)['postgresql_sans_tcp'])


if __name__ == '__main__': unittest.main()
