"""Régressions du refus des extensions de schéma ou de droits non classées."""
import copy
import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('tables',ROOT/'scripts/verifier-tables.py')
tables=importlib.util.module_from_spec(spec);spec.loader.exec_module(tables)

class TablesPrivees(unittest.TestCase):
    def setUp(self):
        self.inventaire={'vision':{'public.prive':{'classe':'contenu-personnel','rls':True,'force_rls':True,
          'colonne_utilisateur':True,'proprietaire':'migration','droits_directs':{'application':['SELECT']}}}}
        self.meta=[dict(copy.deepcopy(self.inventaire['vision']['public.prive']),table='public.prive',politiques=1,droits_colonnes=False)]
        self.roles=[{'nom':'application',**{k:False for k in ('super','bypass','creer_role','creer_base','replication','membre_proprietaire')}}]
    def valider(self):tables.valider('vision',self.meta,self.roles,self.inventaire)
    def test_reference(self):self.valider()
    def test_table_nouvelle_refusee(self):
        nouvelle=copy.deepcopy(self.meta[0]);nouvelle['table']='public.oubliee';self.meta.append(nouvelle)
        with self.assertRaisesRegex(ValueError,'non classées'):self.valider()
    def test_rls_ou_politique_absente(self):
        for k,valeur in [('rls',False),('force_rls',False),('politiques',0)]:
            with self.subTest(k=k):
                avant=self.meta[0][k];self.meta[0][k]=valeur
                with self.assertRaises(ValueError):self.valider()
                self.meta[0][k]=avant
    def test_privilege_proprietaire_et_heritage_refuses(self):
        self.meta[0]['proprietaire']='application'
        with self.assertRaises(ValueError):self.valider()
        self.meta[0]['proprietaire']='migration'
        for k in ('super','bypass','creer_role','creer_base','replication','membre_proprietaire'):
            with self.subTest(k=k):
                self.roles[0][k]=True
                with self.assertRaises(ValueError):self.valider()
                self.roles[0][k]=False
    def test_droits_directs_et_colonnes_refuses(self):
        self.meta[0]['droits_directs']['application'].append('UPDATE')
        with self.assertRaises(ValueError):self.valider()
        self.meta[0]['droits_directs']['application'].pop()
        self.meta[0]['droits_colonnes']=True
        with self.assertRaises(ValueError):self.valider()
    def test_classe_absente_et_role_absent_refuses(self):
        self.inventaire['vision']['public.prive']['classe']=''
        with self.assertRaises(ValueError):self.valider()
        self.inventaire['vision']['public.prive']['classe']='contenu-personnel'
        self.roles=[]
        with self.assertRaises(ValueError):self.valider()

if __name__=='__main__':unittest.main()
