import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

s=importlib.util.spec_from_file_location('confirmer_retour',Path(__file__).resolve().parents[1]/'scripts/monolithe-retour-confirmer.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)


class Confirmer(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.d=Path(self.tmp.name)/('a'*40);self.d.mkdir()
        self.avant={'generation':'ancienne','configuration_sha256':'x','tiers_pids':{'keycloak':'1','nextcloud':'2'}}
        self.actuel=dict(self.avant,tiers_pids={'keycloak':'3','nextcloud':'2'})
        (self.d/'preparation.json').write_text(json.dumps({'avant':self.avant}))
        (self.d/'activation.json').write_text(json.dumps({'phase':'service-demarre','unites_avant':{'vision':'active'}}))
        def exiger(v,message):
            if not v:raise ValueError(message)
        def commande(args,d):return b'0' if 'MainPID' in args else b'active'
        self.stage=SimpleNamespace(exiger=exiger,etat=lambda d:self.actuel,commande=Mock(side_effect=commande),TIERS=('keycloak','nextcloud'))
        self.activer=SimpleNamespace(ecrire=Mock())

    def test_finalisation_sans_copie_sql_ni_redemarrage(self):
        r=m.confirmer(self.d,self.stage,self.activer)
        self.assertEqual(r['processus_tiers_relances'],['keycloak'])
        self.assertFalse(r['nouvelles_copies_effectuees']);self.assertFalse(r['restauration_ancienne_sql'])
        appels=[c.args[0] for c in self.stage.commande.call_args_list]
        self.assertEqual([a for a in appels if 'stop' in a],[['systemctl','stop','mrjam-retour-'+self.d.name[:12]+'.timer']])
        self.assertFalse(any(x in a for a in appels for x in ('restart','start','psql','pg_restore')))

    def test_ecart_configuration_autre_tiers_ou_serveur_actif_refuse_sans_mutation(self):
        for cas in ('configuration','tiers','actif'):
            with self.subTest(cas=cas):
                self.setUp()
                if cas=='configuration':self.actuel['configuration_sha256']='autre'
                if cas=='tiers':self.actuel['tiers_pids']['nextcloud']='4'
                if cas=='actif':self.stage.commande.side_effect=lambda a,d:b'123' if 'MainPID' in a else b'active'
                with self.assertRaises(ValueError):m.confirmer(self.d,self.stage,self.activer)
                self.activer.ecrire.assert_not_called()
                self.assertFalse(any('stop' in c.args[0] for c in self.stage.commande.call_args_list))


if __name__=='__main__':unittest.main()
