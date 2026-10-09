import copy
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import Mock

ROOT=Path(__file__).resolve().parents[1]
def charger(nom,fichier):
    s=importlib.util.spec_from_file_location(nom,ROOT/'scripts'/fichier)
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
m=charger('refus','identite-proprietaire-refus.py')
compte=charger('compte','identite-proprietaire.py')

class RefusExplicite(unittest.TestCase):
    def setUp(self):
        f=json.loads((ROOT/'tests/fixtures/identite-proprietaire-refus-0f8.json').read_text())
        self.sources=f['sources'];self.trace=f['trace'];self.etat={'creation-demandee':{}}
        self.ancien=dict(version=1,objet='mrjam-enrolement-proprietaire',issuer=compte.ISSUER,
            courriel='profil@example.test',nom_connexion='AB')
        self.contact={**self.ancien,'nom_connexion':'AB.MrJam'};self.personnes=[]
        self.profil=json.loads((ROOT/'operations/identite/profil.json').read_text())
    def effectuer(self):
        return m.verifier(self.trace,self.sources,self.ancien,self.contact,self.etat,self.personnes,self.profil)
    def test_post400_exact_sans_sujet_ni_mail(self):
        self.assertTrue(self.effectuer()['post_creation_refuse_http400'])
    def test_transport_ou_code_inattendu_ne_sont_pas_refus_de_creation(self):
        for fin in ('urllib.error.URLError: <urlopen error timed out>',
            'TimeoutError: timed out','urllib.error.HTTPError: HTTP Error 503: Service Unavailable'):
            self.setUp();self.trace=self.trace.rsplit('urllib.error.HTTPError:',1)[0]+fin+'\n'
            with self.subTest(fin=fin),self.assertRaises(m.RepriseRefusee):self.effectuer()
    def test_refus_courriel_et_autre_etape_ne_sont_pas_creation(self):
        for ligne in (29,51,60):
            self.setUp();self.trace=self.trace.replace('line 34,','line '+str(ligne)+',')
            with self.subTest(ligne=ligne),self.assertRaises(m.RepriseRefusee):self.effectuer()
    def test_source_alteree_et_tracebacks_multiples_refuses(self):
        self.sources['identite-proprietaire.py']+='\n# différent\n'
        with self.assertRaises(m.RepriseRefusee):self.effectuer()
        self.setUp();self.trace+=self.trace
        with self.assertRaises(m.RepriseRefusee):self.effectuer()
    def test_sujet_ou_intention_courriel_interdisent_la_reprise(self):
        for k in ('compte.json','courriel-demande','courriel-accepte'):
            self.setUp();self.etat[k]={}
            with self.subTest(k=k),self.assertRaises(m.RepriseRefusee):self.effectuer()
    def test_reprise_consomme_interdit_une_nouvelle_intention_ambigue(self):
        for k in (m.ARCHIVE,m.RECU):
            self.setUp();self.etat[k]={}
            with self.subTest(k=k),self.assertRaises(m.RepriseRefusee):self.effectuer()
    def test_compte_non_receipte_ou_intention_absente_refuses(self):
        self.personnes=[{'id':'inconnu'}]
        with self.assertRaises(m.RepriseRefusee):self.effectuer()
        self.setUp();self.etat={}
        with self.assertRaises(m.RepriseRefusee):self.effectuer()
    def test_meme_adresse_et_issuer_obligatoires(self):
        for cle,valeur in (('courriel','autre@example.test'),('issuer','https://autre.example.test')):
            self.setUp();self.contact[cle]=valeur
            with self.subTest(cle=cle),self.assertRaises(m.RepriseRefusee):self.effectuer()
    def test_profil_modifie_refuse_sans_affaiblissement(self):
        for cle,valeur in (('min',2),('min',4),('max',256)):
            self.setUp();self.profil['attributes'][0]['validations']['length'][cle]=valeur
            with self.subTest(cle=cle,valeur=valeur),self.assertRaises(m.RepriseRefusee):self.effectuer()
    def test_identifiant_trop_court_refuse_avant_api_et_intention(self):
        api=Mock();ecrire=Mock()
        with self.assertRaises(ValueError):compte.preparer_compte(api,self.ancien,{}.get,ecrire)
        api.assert_not_called();ecrire.assert_not_called()

if __name__=='__main__':unittest.main()
