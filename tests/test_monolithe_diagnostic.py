import importlib.util
from pathlib import Path
import unittest
import json
from unittest.mock import patch
from types import SimpleNamespace

s=importlib.util.spec_from_file_location('diagnostic',Path(__file__).resolve().parents[1]/'scripts/monolithe-diagnostic.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)


class Diagnostic(unittest.TestCase):
    def test_traversee_exacte_sous_vision_sans_lire_de_fichier(self):
        for code in (0,1):
            with patch.object(m.subprocess,'run',return_value=SimpleNamespace(returncode=code)) as run:
                self.assertEqual(m.acces_parent_restauration(),code==0)
                self.assertEqual(run.call_args.args[0],['runuser','-u','vision','--','test','-x','/var/lib/postgresql'])
        with patch.object(m.subprocess,'run',return_value=SimpleNamespace(returncode=2)):
            with self.assertRaisesRegex(ValueError,'indisponible'):m.acces_parent_restauration()

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

    def test_condition_privee_ne_revele_ni_message_ni_ligne_source(self):
        t='Traceback (most recent call last):\n  File "/root/prive/script.py", line 42, in qualifier\n    contenu_personnel = secret\nValueError: contenu_personnel et secret'
        r=m.diagnostic_erreur(t)
        self.assertEqual(r,{'exception':'ValueError','pile':[{'fichier':'script.py','ligne':42}]})
        self.assertNotIn('secret',json.dumps(r))
        self.assertNotIn('prive',json.dumps(r))

    def test_seul_champ_de_contrat_de_table_versionnee_est_emis(self):
        t='ValueError: Contrat SQL divergent : public.vision_items force_rls'
        r=m.diagnostic_erreur(t,{'public.vision_items'})
        self.assertEqual(r['contrat_sql'],{'table':'public.vision_items','champ':'force_rls'})
        self.assertNotIn('contrat_sql',m.diagnostic_erreur(t,{'public.autre'}))
        self.assertNotIn('contrat_sql',m.diagnostic_erreur(t+' contenu_prive',{'public.vision_items'}))

    def test_metadonnees_uniquement_et_tables_versionnees(self):
        rows=[{'table':t,'rls':True,'force_rls':True,'colonne_utilisateur':True,'politiques':1}
              for t in ('public.vision_contextes','public.inconnue_privee')]
        with patch.object(m.subprocess,'run',return_value=SimpleNamespace(stdout=json.dumps(rows))) as run:
            r=m.metadonnees_rls('/nix/store/postgres','vision',{'public.vision_contextes'})
        self.assertEqual(set(r),{'public.vision_contextes'})
        self.assertIn('BEGIN READ ONLY',run.call_args.kwargs['input'])
        self.assertNotIn('FROM public.',run.call_args.kwargs['input'])
        with self.assertRaises(ValueError):m.metadonnees_rls('/nix/store/postgres','autre',{})


if __name__=='__main__':unittest.main()
