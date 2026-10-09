import copy,importlib.util,unittest
from pathlib import Path
s=importlib.util.spec_from_file_location('garde',Path(__file__).resolve().parents[1]/'scripts/vision-amorcage-reprise.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

class Reprise(unittest.TestCase):
    def fixture(self):
        return dict(revision=m.REVISION,socle_conserve=True,retour_termine=True,cluster_prive_present=True,
          generation_enregistree=False,activation=False,inscriptions=False,categories=['commande_refusee'],
          worker=dict(etat='failed',code=1),controle_worker=dict(etapes=['essai_generation'],categories=[]),
          unites_echec=dict(bilan_present=True,connues=['nginx.service'],inconnues=0),
          cluster=dict(present=True,dossier_prive=True,version17=True,controle_disponible=True,journal_disponible=True,
            etat='shut down',pid_present=False,socket_present=False,categories=[]),
          import_prive=dict(import_verifie=True,secret_amorcage_format_verifie=True))
    def test_preuve_fermee(self):self.assertTrue(m.verifier(self.fixture()))
    def test_toute_divergence_refuse_la_reprise(self):
        changements=[('revision','0'*40),('socle_conserve',False),('retour_termine',False),
          ('generation_enregistree',True),('activation',True),('inscriptions',True),('categories',[]),
          ('worker',dict(etat='active',code=0)),('worker',dict(etat='failed',code=999)),
          ('controle_worker',dict(etapes=['controles_locaux'],categories=[])),
          ('unites_echec',dict(bilan_present=True,connues=['nginx.service','vision.service'],inconnues=0)),
          ('import_prive',dict(import_verifie=False,secret_amorcage_format_verifie=True))]
        for k,v in changements:
            r=self.fixture();r[k]=v
            with self.subTest(champ=k),self.assertRaises(ValueError):m.verifier(r)
        for k,v in [('etat','in production'),('pid_present',True),('socket_present',True),
          ('dossier_prive',False),('version17',False),('categories',['cluster_prive_echec'])]:
            r=self.fixture();r['cluster'][k]=v
            with self.subTest(cluster=k),self.assertRaises(ValueError):m.verifier(r)

if __name__=='__main__':unittest.main()
