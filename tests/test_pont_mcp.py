"""Garde de routage du pont : aucun serveur Lisp ni calcul applicatif requis."""
import importlib.util
import copy
import hashlib
import json
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
    def reference_synthetique(self):
        trace=[{'outil':outil,'nom':nom,'arguments':{}} for outil,noms in
               [('cl-mcp',['load-system','run-tests','repl-eval']),
                ('tron',['repl_eval','repl_compile','repl_frame_locals','repl_get_restarts','repl_invoke_restart'])]
               for nom in noms]
        preuve={'format':1,'resultat':'succes','confiance':'locale-non-attestee','autorise_publication':False,
            'mutation_cl_mcp':11,'mutation_tron':12,'locaux':{'base':40,'facteur':2},
            'effets_avant_erreur':1,'effets_apres_restart':1,'resultat_calcul':42,
            'sources':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in qualification.ENTREES_REFERENCE},
            'trace_sha256':hashlib.sha256(json.dumps(trace,sort_keys=True).encode()).hexdigest()}
        return preuve,trace

    def test_validation_reference_sans_appel_ni_reinitialisation(self):
        preuve,trace=self.reference_synthetique()
        with patch.object(qualification.pont,'envoyer') as envoyer:
            r=qualification.verifier_reference(preuve,trace)
            self.assertFalse(r['scenario_reexecute'])
            self.assertFalse(r['connexion_actuelle_verifiee'])
            envoyer.assert_not_called()

    def test_preuve_alteree_ou_entrees_modifiees_refusees(self):
        preuve,trace=self.reference_synthetique()
        for cle,valeur in [('resultat','echec'),('effets_apres_restart',2),('trace_sha256','0'*64)]:
            modifiee=copy.deepcopy(preuve);modifiee[cle]=valeur
            with self.subTest(cle=cle),self.assertRaises(ValueError):qualification.verifier_reference(modifiee,trace)
        modifiee=copy.deepcopy(preuve);modifiee['sources']['tests/outils-mcp/scenario.lisp']='0'*64
        with self.assertRaises(ValueError):qualification.verifier_reference(modifiee,trace)

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
