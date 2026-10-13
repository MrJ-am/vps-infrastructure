import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import hashlib
import json
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('connexion_test',ROOT/'scripts/log-connexion-promouvoir.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)


class Correction(unittest.TestCase):
    def fixture(self):
        avant=dict(generation='native-avant',demarrage='native-avant')
        r=dict(avant='native-avant',invariants=True,assertions=True,nativeActif=True,
               extraAvant='add_header Referrer-Policy "no-referrer" always;',
               extraApres='add_header Referrer-Policy "strict-origin" always;',
               proxyAvant='proxy_ssl_verify on;',proxyApres='proxy_ssl_verify on;\nproxy_hide_header Referrer-Policy;')
        return avant,r
    def test_eval_preserve_native_et_refuse_autre_changement(self):
        avant,r=self.fixture();m.verifier_evaluation(r,avant)
        for key,value in [('invariants',False),('assertions',False),('nativeActif',False),
             ('avant','ancien-keycloak'),('extraApres','no-referrer'),('proxyApres','proxy_ssl_verify off;')]:
            with self.subTest(key=key),self.assertRaises(ValueError):
                m.verifier_evaluation(dict(r,**{key:value}),avant)
    def test_boot_profile_concurrent_refuse(self):
        avant,r=self.fixture()
        with self.assertRaises(ValueError):m.verifier_evaluation(r,dict(avant,demarrage='autre'))
    def test_retour_native_sans_restauration_de_compte_ou_base(self):
        stage=SimpleNamespace(etat=lambda _:dict(generation='native-candidat'),commande=Mock())
        plan=dict(avant=dict(generation='native-avant',configuration_lien='/fixture/ancienne.nix'),candidat='native-candidat')
        with patch.object(m,'configuration') as config,patch.object(m,'ecrire') as preuve:
            m.retour(Path('/fixture'),stage,plan)
            config.assert_called_once_with('/fixture/ancienne.nix')
            calls=[c.args[0] for c in stage.commande.call_args_list]
            self.assertEqual(calls,[['nix-env','-p','/nix/var/nix/profiles/system','--set','native-avant'],
                ['native-avant/bin/switch-to-configuration','switch']])
            self.assertTrue(preuve.call_args.args[1]['identites_et_donnees_non_restaurees'])
    def test_retour_refuse_generation_concurrente(self):
        stage=SimpleNamespace(etat=lambda _:dict(generation='concurrente'),commande=Mock())
        with patch.object(m,'configuration') as config,self.assertRaises(ValueError):
            m.retour(Path('/fixture'),stage,dict(avant=dict(generation='native-avant'),candidat='native-candidat'))
        config.assert_not_called();stage.commande.assert_not_called()

class Provenance(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0,str(ROOT/'scripts'))
        spec=importlib.util.spec_from_file_location('connexion_ci_test',ROOT/'scripts/log-operation.py')
        self.ci=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.ci)
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);(self.root/'operations').mkdir()
        self.sources={nom:(ROOT/nom).read_text() for nom in m.FICHIERS}
        for nom,source in self.sources.items():
            (self.root/nom).parent.mkdir(exist_ok=True);(self.root/nom).write_text(source)
        self.suites={nom:{'commandes':[['fixture']]} for nom in ('log-routage-nix','log-connexion')}
        self.p=dict(format=1,origine_preuves='codex-local-non-attestee',soumission_autorisee_par_proprietaire=True,
             revision_sources='a'*40,revision_assemblage='b'*40,artefact_sha256='c'*64,generation_attendue='native-active',
             empreintes={nom:hashlib.sha256(source.encode()).hexdigest() for nom,source in self.sources.items()},
             recus={nom:dict(format=1,resultat='succes',confiance='locale-non-attestee',autorise_publication=False,codes=[0],
               identite=dict(definition=hashlib.sha256(json.dumps(suite,sort_keys=True).encode()).hexdigest(),entrees='fixture'))
               for nom,suite in self.suites.items()})
    def appel(self):
        (self.root/'operations/log-connexion-candidat.json').write_text(json.dumps(self.p))
        with patch.object(self.ci,'ROOT',self.root),patch('assemblage.catalogue',return_value=self.suites),\
             patch('assemblage.entrees',return_value='fixture'),\
             patch.object(self.ci.subprocess,'check_output',side_effect=lambda args,**_:self.sources[args[2].split(':',1)[1]].encode()),\
             patch.object(self.ci.stage,'descriptor',return_value=dict(revision_operateurs='b'*40,artefact_sha256='c'*64)),\
             patch.object(self.ci.stage,'manifeste',return_value=dict(toolchain=dict(production=dict(nixpkgs='/fixture')))):
            self.ci.correction_connexion()
    def test_chemin_qualifie_envoie_sources_exactes_sans_bascule_identite(self):
        with patch.object(self.ci.stage,'ssh') as ssh,patch.object(self.ci.stage,'main') as preparation:
            self.appel();preparation.assert_not_called()
            self.assertIn(b'correction_connexion_ci',ssh.call_args.kwargs['input'])
            self.assertNotIn(b'log-activer.py',ssh.call_args.kwargs['input'])
    def test_entrees_modifiees_refusees_avant_ssh(self):
        for cas in ('recu','empreinte','definition','codes_vides'):
            self.setUp()
            if cas=='recu':self.p['recus']['log-connexion']['resultat']='echec'
            if cas=='empreinte':self.p['empreintes'][m.FICHIERS[0]]='0'*64
            if cas=='definition':self.p['recus']['log-connexion']['identite']['definition']='0'*64
            if cas=='codes_vides':self.p['recus']['log-connexion']['codes']=[]
            with self.subTest(cas=cas),patch.object(self.ci.stage,'ssh') as ssh,self.assertRaises(ValueError):self.appel()
            ssh.assert_not_called()

if __name__=='__main__':unittest.main()
