import importlib.util
import unittest
from pathlib import Path

s=importlib.util.spec_from_file_location('proprietaire',Path(__file__).resolve().parents[1]/'scripts/identite-proprietaire.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

class Enrolement(unittest.TestCase):
    def setUp(self):
        self.etat={};self.comptes=[];self.envois=0;self.creations=0;self.admin=False
        self.identite=dict(version=1,objet='mrjam-enrolement-proprietaire',issuer=m.ISSUER,
            courriel='synthetique@example.test',nom_connexion='Synthétique')
        self.identite['nom_connexion']='Synthese'
    def api(self,path,body=None,method=None):
        if method=='POST':
            assert 'creation-demandee' in self.etat
            self.creations+=1
            self.comptes=[body|{'id':'a'*8+'-'+'b'*4+'-'+'c'*4+'-'+'d'*4+'-'+'e'*12,'username':'synthese'}]
            return 201,None,{'Location':'http://127.0.0.1:8085/admin/realms/mrjam/users/'+self.comptes[0]['id']}
        if method=='PUT':
            assert 'courriel-demande' in self.etat
            assert body==m.ACTIONS and 'lifespan=1800' in path and 'client_id=account-console' in path
            self.envois+=1
            return 204,None,{}
        if path.endswith('/users?max=2'):return self.comptes
        if path.endswith('/clients?clientId=realm-management'):return [{'id':'f'*8+'-'+'a'*4+'-'+'b'*4+'-'+'c'*4+'-'+'d'*12}]
        if path.endswith('/composite'):return [{}] if self.admin else []
        if path.endswith('/credentials'):return []
        return self.comptes[0]
    def effectuer(self):
        return m.preparer_compte(self.api,self.identite,self.etat.get,lambda k,v:self.etat.__setitem__(k,v))
    def test_aucun_mot_de_passe_ni_admin_et_aucun_rejeu(self):
        for _ in range(2):
            r=self.effectuer()
            self.assertTrue(r['participation_proprietaire_requise'])
            self.assertFalse(r['mot_de_passe_fourni_par_exploitation'])
        self.assertEqual((self.creations,self.envois),(1,1))
        self.assertNotIn('credentials',self.comptes[0]);self.assertFalse(self.comptes[0]['emailVerified'])
    def test_courriel_canonique_du_fournisseur_native(self):
        self.identite['courriel']='Synthese@Example.test'
        self.effectuer();self.effectuer()
        self.assertEqual(self.etat['compte.json']['courriel'],'synthese@example.test')
        self.assertEqual((self.creations,self.envois),(1,1))

    def test_reponse_creation_perdue_ne_devient_pas_association_par_email(self):
        self.etat['creation-demandee']={}
        with self.assertRaises(ValueError):self.effectuer()
        self.assertEqual((self.creations,self.envois),(0,0))
    def test_reponse_courriel_perdue_ne_declenche_pas_second_envoi(self):
        self.effectuer();del self.etat['courriel-accepte']
        with self.assertRaises(ValueError):self.effectuer()
        self.assertEqual((self.creations,self.envois),(1,1))
    def test_compte_etranger_ou_droit_identite_bloque_envoi(self):
        self.comptes=[{'id':'autre'}]
        with self.assertRaises(ValueError):self.effectuer()
        self.assertEqual((self.creations,self.envois),(0,0))
        self.comptes=[];self.admin=True
        with self.assertRaises(ValueError):self.effectuer()
        self.assertEqual((self.creations,self.envois),(1,0))

    def test_creation_inattendue_ne_valide_ni_compte_ni_courriel(self):
        for code,identifiant in ((202,'a'*8+'-'+'b'*4+'-'+'c'*4+'-'+'d'*4+'-'+'e'*12),(201,'-'*36)):
            self.setUp()
            def api(path,body=None,method=None):
                r=self.api(path,body,method)
                if method=='POST':return code,None,{'Location':'http://127.0.0.1:8085/admin/realms/mrjam/users/'+identifiant}
                return r
            with self.assertRaises(ValueError):m.preparer_compte(api,self.identite,self.etat.get,lambda k,v:self.etat.__setitem__(k,v))
            self.assertIn('creation-demandee',self.etat);self.assertNotIn('compte.json',self.etat);self.assertEqual(self.envois,0)

    def test_courriel_non_accepte_ne_marque_pas_succes_ni_rejeu(self):
        def api(path,body=None,method=None):
            r=self.api(path,body,method)
            return (202,None,{}) if method=='PUT' else r
        with self.assertRaises(ValueError):m.preparer_compte(api,self.identite,self.etat.get,lambda k,v:self.etat.__setitem__(k,v))
        self.assertNotIn('courriel-accepte',self.etat);self.assertIn('courriel-demande',self.etat)
        with self.assertRaises(ValueError):self.effectuer()
        self.assertEqual((self.creations,self.envois),(1,1))

if __name__=='__main__':unittest.main()
