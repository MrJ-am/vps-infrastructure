"""Refus/reprise des effets incertains, sans VPS ni mail réel."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('operation_log',ROOT/'scripts/log-activer.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

class Reprise(unittest.TestCase):
    def test_diagnostic_classe_erreur_sans_publier_les_valeurs(self):
        spec=importlib.util.spec_from_file_location('log_diag_test',ROOT/'scripts/log-diagnostic.py')
        diag=importlib.util.module_from_spec(spec);spec.loader.exec_module(diag)
        spec=importlib.util.spec_from_file_location('diag_existant_test',ROOT/'scripts/monolithe-diagnostic.py')
        ancien=importlib.util.module_from_spec(spec);spec.loader.exec_module(ancien)
        secret='SecretSyntheseJamaisPublie'
        out=diag.classifier("error: attribute 'version' missing\n at /fixture/log.nix:12:5\n services.kanidm.package\n value: "+secret,ancien)
        self.assertEqual(out['attributs_absents'],['version'])
        self.assertNotIn(secret,json.dumps(out))
    def plan(self):
        return dict(ancien_compte={'utilisateur':'alice'},ancien_lien={'emetteur':'ancien','sujet':'avant'},subject='nouveau')
    def test_commit_apres_timeout_est_constate_et_retourne(self):
        p=self.plan()
        with patch.object(m,'sql',return_value={'emetteur':m.NEW_ISSUER,'sujet':'nouveau'}),patch.object(m,'rattacher') as r:
            m.retablir_rattachement(p);r.assert_called_once_with(p,retour=True)
    def test_commit_absent_ne_fabrique_pas_de_changement(self):
        with patch.object(m,'sql',return_value={'emetteur':'ancien','sujet':'avant'}),patch.object(m,'rattacher') as r:
            m.retablir_rattachement(self.plan());r.assert_not_called()
    def test_ecriture_concurrente_ne_se_fait_pas_ecraser(self):
        with patch.object(m,'sql',return_value={'emetteur':'autre','sujet':'concurrent'}),patch.object(m,'rattacher') as r:
            with self.assertRaises(ValueError):m.retablir_rattachement(self.plan())
            r.assert_not_called()
    def test_mail_resultat_incertain_interdit_repetition(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'courriel-log.json').write_text(json.dumps({'envoi_engage':True,'accepte_par_relais':False}))
            with patch.object(m,'module') as imports:
                with self.assertRaises(ValueError):m.envoyer(p,{}, {}, {})
                imports.assert_not_called()
    def test_mail_deja_accepte_ne_se_renvoie_pas(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'courriel-log.json').write_text(json.dumps({'accepte_par_relais':True}))
            with patch.object(m,'module') as imports:
                self.assertTrue(m.envoyer(p,{}, {}, {})['accepte_par_relais']);imports.assert_not_called()
    def test_nombre_personnes_tronque_est_refuse(self):
        def api(path):
            if path=='/admin/realms':return [{'realm':'master'},{'realm':'mrjam'}]
            if path.endswith('/mrjam/'):return {}
            if path.endswith('/clients'):return []
            return [{'serviceAccountClientId':'fixture'}]*100
        with self.assertRaises(ValueError):m.inventorier_ancien(api)
    def test_consommateur_supplementaire_est_preserve(self):
        def api(path):
            if path=='/admin/realms':return [{'realm':'master'},{'realm':'mrjam'}]
            return {} if path.endswith('/mrjam/') else [{'clientId':'hors-perimetre'}]
        with self.assertRaises(ValueError):m.inventorier_ancien(api)
    def test_realm_supplementaire_arrete_avant_toute_mutation(self):
        appels=[]
        def api(path):
            appels.append(path)
            return [{'realm':'master'},{'realm':'mrjam'},{'realm':'tiers'}]
        with self.assertRaisesRegex(ValueError,'Realm IdP supplémentaire'):
            m.inventorier_ancien(api)
        self.assertEqual(appels,['/admin/realms'])

if __name__=='__main__': unittest.main()
