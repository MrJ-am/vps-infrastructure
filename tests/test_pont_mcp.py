"""Garde de routage du pont : aucun serveur Lisp ni calcul applicatif requis."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('pont',ROOT/'scripts/mcp-appel.py')
pont=importlib.util.module_from_spec(spec);spec.loader.exec_module(pont)
qualification_spec=importlib.util.spec_from_file_location('qualification',ROOT/'scripts/qualifier-mcp.py')
qualification=importlib.util.module_from_spec(qualification_spec);qualification_spec.loader.exec_module(qualification)


class Routage(unittest.TestCase):
    def test_locaux_fallbacks_et_commande_inconnue_refuses_avant_transport(self):
        for nom in ('inspect_object','inspect_package','runtime_stats','thread_list',
                    'reload_system','code_compile_string','swank_launch','inconnu'):
            with self.subTest(nom=nom),patch.object(pont,'envoyer') as envoyer:
                with self.assertRaises(ValueError):
                    pont.requete('tron','tools/call',{'name':nom,'arguments':{}})
                envoyer.assert_not_called()

    def test_connexion_explicitement_locale_obligatoire(self):
        for args in ({},{'type':'auto','host':'127.0.0.1','port':4105},
                     {'type':'swank','host':'ailleurs','port':4105},
                     {'type':'swank','host':'127.0.0.1','port':4005}):
            with self.subTest(args=args),self.assertRaises(ValueError):
                pont.verifier_commande('tron','tools/call',{'name':'repl_connect','arguments':args})
        pont.verifier_commande('tron','tools/call',{'name':'repl_connect',
            'arguments':{'type':'swank','host':'127.0.0.1','port':4105}})

    def evaluer(self,statut):
        with tempfile.TemporaryDirectory() as tmp,patch.object(pont,'ETAT',Path(tmp)):
            (Path(tmp)/'tron-session.json').write_text('{"session":"synthetique"}')
            def reponse(url,message,session):
                nom=message['params']['name']
                if nom=='repl_eval':self.assertEqual(message['params']['arguments'],{'code':'(+ 1 2)'})
                result={'content':[{'type':'text','text':statut if nom=='repl_status' else 'RESULTAT'}]}
                return {'result':result},None
            with patch.object(pont,'envoyer',side_effect=reponse) as envoyer:
                try:
                    res=pont.requete('tron','tools/call',{'name':'repl_eval','arguments':{'code':'(+ 1 2)'}})
                    return res,[c.args[1]['params']['name'] for c in envoyer.call_args_list]
                except ValueError:
                    return None,[c.args[1]['params']['name'] for c in envoyer.call_args_list]

    def test_deconnexion_ou_mauvaise_cible_ne_transmet_pas_evaluation(self):
        for statut in ('(CONNECTED NIL)','(CONNECTED T TYPE SWANK HOST ailleurs PORT 4105)',
                       '(CONNECTED T TYPE SWANK HOST 127.0.0.1 PORT 4005)',
                       '(ERROR T MESSAGE "échec")'):
            with self.subTest(statut=statut):
                res,appels=self.evaluer(statut)
                self.assertIsNone(res);self.assertEqual(appels,['repl_status'])

    def test_cible_etablie_preserve_code_et_resultat(self):
        res,appels=self.evaluer('(CONNECTED T TYPE SWANK\n HOST 127.0.0.1 PORT 4105)')
        self.assertEqual(appels,['repl_status','repl_eval'])
        self.assertEqual(pont.texte(res),'RESULTAT')

    def test_cl_mcp_et_catalogue_restant_accessibles(self):
        pont.verifier_commande('cl-mcp','tools/call',{'name':'load-system'})
        pont.verifier_commande('tron','tools/list',{})

    def test_restart_de_fixture_reconnu_par_sens_position_et_cible(self):
        attendu='(RESTARTS\n ((RECALCULER Recalculer seulement, sans répéter l’effet déjà exécuté.) (ABORT Abandonner.)) THREAD 5 LEVEL 1)'
        self.assertEqual(qualification.restart_fixture(attendu),{'index':0,'thread':5,'niveau':1})
        for texte in (attendu.replace('RECALCULER','RETRY'),
                      attendu.replace('sans répéter','en répétant'),
                      attendu.replace('((RECALCULER','((RETRY Réessayer.) (RECALCULER'),
                      attendu.replace('THREAD 5 LEVEL 1','THREAD NIL LEVEL 0')):
            with self.subTest(texte=texte),self.assertRaises(ValueError):
                qualification.restart_fixture(texte)


if __name__=='__main__':unittest.main()
