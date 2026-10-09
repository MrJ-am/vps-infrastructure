"""Réponses synthétiques capturées sur Keycloak26.7.3 et PostgreSQL17."""
import copy
import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
def charger(nom,fichier):
    s=importlib.util.spec_from_file_location(nom,ROOT/'scripts'/fichier)
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
m=charger('observation','vision-proprietaire-observation.py')
notes=charger('notes','identite-session-proprietaire.py')

class FluxNatif(unittest.TestCase):
    def setUp(self):
        self.f=json.loads((ROOT/'tests/fixtures/identite-flux-natif.json').read_text())
        self.sql={c['alias']:c['config'] for c in self.f['modele']['authenticatorConfig']
            if c['alias'] in ('mrjam-mot-de-passe','mrjam-second-facteur','mrjam-lien-courriel')}
    def api(self,path):
        if path.endswith('/executions'):return self.f['executions']
        return self.f['configs'][path.rsplit('/',1)[1]]
    def effectuer(self):
        with patch.object(m,'sql_prive',return_value=self.sql):
            return m.executions(self.api,'/runuser','/psql',self.f['modele'])
    def execution(self,provider):
        return next(e for e in self.f['executions'] if e.get('providerId')==provider)
    def test_flux_natif_et_valeurs_masquees(self):
        self.assertEqual(self.execution('auth-username-password-form')['requirement'],'ALTERNATIVE')
        self.assertEqual(self.execution('auth-otp-form')['requirement'],'REQUIRED')
        self.assertTrue(all(v=='**********' for c in self.f['configs'].values() for v in c['config'].values()))
        self.assertEqual(set(self.effectuer()),{'pwd','otp'})
    def test_otp_non_obligatoire_et_identification_desactivee_refuses(self):
        for provider,requirement in (('auth-otp-form','ALTERNATIVE'),('auth-username-password-form','DISABLED'),('mrjam-courriel','REQUIRED')):
            self.setUp();self.execution(provider)['requirement']=requirement
            with self.subTest(provider=provider),self.assertRaises(m.ObservationRefusee):self.effectuer()
    def test_sous_flux_bypass_ou_deplace_refuse(self):
        for champ,valeur in (('requirement','ALTERNATIVE'),('level',0),('priority',99),('displayName','browser')):
            self.setUp();e=next(x for x in self.f['executions'] if x.get('displayName')=='mrjam-identification');e[champ]=valeur
            with self.subTest(champ=champ),self.assertRaises(m.ObservationRefusee):self.effectuer()
    def test_provider_et_execution_supplementaire_refuses(self):
        self.execution('mrjam-courriel')['providerId']='auth-cookie'
        with self.assertRaises(m.ObservationRefusee):self.effectuer()
        self.setUp();self.f['executions'].append(copy.deepcopy(self.f['executions'][-1]))
        with self.assertRaises(m.ObservationRefusee):self.effectuer()
    def test_identifiants_dupliques_et_config_injectee_refuses(self):
        self.execution('auth-otp-form')['id']=self.execution('auth-username-password-form')['id']
        with self.assertRaises(m.ObservationRefusee):self.effectuer()
        self.setUp();self.execution('auth-otp-form')['authenticationConfig']='../../secret'
        with self.assertRaises(m.ObservationRefusee):self.effectuer()
    def test_api_masquee_ne_remplace_pas_verification_sql(self):
        for alias,cle,valeur in (('mrjam-mot-de-passe','default.reference.value','email'),
            ('mrjam-second-facteur','default.reference.maxAge','3600'),('mrjam-lien-courriel','ajout','inattendu')):
            self.setUp();self.sql[alias][cle]=valeur
            with self.subTest(alias=alias),self.assertRaises(m.ObservationRefusee):self.effectuer()
    def test_mauvaise_config_api_refusee(self):
        cfg=self.f['configs'][self.execution('auth-otp-form')['authenticationConfig']]
        cfg['config']['default.reference.value']='pwd'
        with self.assertRaises(m.ObservationRefusee):self.effectuer()
    def test_lien_magique_et_presence_otp_ne_sont_pas_preuve_pwd(self):
        ids=self.effectuer();maintenant=1700000000
        donnees={'authMethod':'openid-connect','notes':{'AUTH_TIME':str(maintenant),
            'authenticators-completed':json.dumps({ids['pwd'][0]:maintenant,ids['otp'][0]:maintenant})}}
        self.assertTrue(notes.verifier_notes(donnees,ids,maintenant))
        self.assertFalse(notes.verifier_notes(donnees,ids,maintenant+301))
        donnees['notes']['authenticators-completed']=json.dumps({self.execution('mrjam-courriel')['id']:maintenant,ids['otp'][0]:maintenant})
        self.assertFalse(notes.verifier_notes(donnees,ids,maintenant))

if __name__=='__main__':unittest.main()
