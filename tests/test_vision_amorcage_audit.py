"""La classification technique ne recopie ni unité inconnue ni données privées."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


def charger(nom):
    s = importlib.util.spec_from_file_location(nom, ROOT/'scripts'/(nom+'.py'))
    m = importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


audit = charger('vision-identite-amorcage-auditer')
plan = charger('vision-plan')


class Audit(unittest.TestCase):
    def test_sortie_sans_fragment_prive_et_avec_unites_connues(self):
        secret = 'valeur-utilisateur-confidentielle'
        r = audit.classer('RuntimeError: Dry-activate annonce une unité étrangère '+secret,
            'would activate the configuration...\nwould restart the following units: nscd.service, '+secret+'.service\n')
        self.assertEqual(r['categories'],['unite_etrangere'])
        self.assertEqual(r['unites']['restart'],dict(connues=['nscd.service'],acme=0,inconnues=1))
        self.assertNotIn(secret,json.dumps(r))

    def test_diagnostic_inconnu_et_acme_ne_fuient_pas(self):
        r = audit.classer('trace-privee-indeterminee','would reload the following units: acme-domaine-prive.service\n')
        self.assertEqual(r['categories'],[]);self.assertEqual(r['unites']['reload'],dict(connues=[],acme=1,inconnues=0))
        self.assertNotIn('domaine-prive',json.dumps(r))

    def test_exception_reelle_du_controle_est_classee(self):
        r = audit.classer('construction_identite.ConstructionRefusee: Dry-activate annonce une unité étrangère à l’amorçage', '')
        self.assertEqual(r['categories'],['unite_etrangere'])

    def test_retour_non_etabli_interdit_lecture(self):
        etat=dict(commence=True, **{'plan.json':True,'retour-commence':True,'retour-termine':True,'enregistre':False})
        audit.verifier_retour(etat)
        for nom in etat:
            with self.subTest(nom=nom),self.assertRaises(ValueError):
                audit.verifier_retour(etat|{nom:not etat[nom]})
        with self.assertRaises(ValueError):audit.verifier_retour({})

    def test_trace_worker_et_journal_ne_sortent_que_etapes_et_motifs_fermes(self):
        secret='valeur-confidentielle'
        texte='{"etape": "essai_generation"}\n{"etape": "'+secret+'"}\nModuleNotFoundError: '+secret+'\nFailed at step EXEC '+secret
        r=audit.classer_worker(texte)
        self.assertEqual(r['etapes'],['essai_generation'])
        self.assertEqual(r['categories'],['lancement_python_refuse','bibliotheque_python_absente'])
        self.assertNotIn(secret,json.dumps(r))

    def test_worker_actif_et_etat_indetermine_refuses(self):
        for sortie,code in ((b'ActiveState=active\nExecMainStatus=0\n',0),
                (b'ActiveState=inactive\nExecMainStatus=donnee-privee\n',0),
                (b'ActiveState=inactive\nExecMainStatus=256\n',0),(b'',1)):
            with patch.object(audit.subprocess,'run',return_value=SimpleNamespace(stdout=sortie,returncode=code)) as appel:
                with self.assertRaises(ValueError):audit.etat_worker(Path('/outils'))
                self.assertEqual(appel.call_count,1)
        valeurs=[SimpleNamespace(stdout=b'ActiveState=failed\nExecMainStatus=203\n',returncode=0),
            SimpleNamespace(stdout=b'journal-prive',returncode=0)]
        with patch.object(audit.subprocess,'run',side_effect=valeurs):
            self.assertEqual(audit.etat_worker(Path('/outils')),(dict(etat='failed',code=203),'journal-prive'))

    def test_reprise_exige_la_trace_exacte_et_absence_de_cluster_ou_etape(self):
        prive='contenu-prive-inconnu'
        trace='essai = Essai(a.revision); getattr(essai, a.action)()\n'+prive+"\nTypeError: 'str' object is not callable\nValueError: Délai d’essai dépassé"
        resultat=audit.classer(trace,'')
        self.assertEqual(set(resultat['categories']),{'action_masquee','essai_timeout'})
        self.assertNotIn(prive,json.dumps(resultat))
        self.assertEqual(audit.classer("TypeError: 'str' object is not callable",'')['categories'],[])
        rapport=dict(revision=audit.REVISION,socle_conserve=True,retour_termine=True,
            generation_enregistree=False,activation=False,inscriptions=False,cluster_prive_present=False,
            worker=dict(etat='inactive'),controle_worker=dict(etapes=[],categories=[]),**resultat)
        audit.verifier_reprise(rapport)
        for cle,valeur in (('revision','a'*40),('socle_conserve',False),('retour_termine',False),
                ('generation_enregistree',True),('activation',True),('inscriptions',True),('cluster_prive_present',True),
                ('categories',['essai_timeout']),('categories',['action_masquee','essai_timeout','commande_refusee']),
                ('worker',dict(etat='active')),('controle_worker',dict(etapes=['essai_generation'],categories=[])),
                ('controle_worker',dict(etapes=[],categories=['commande_refusee']))):
            with self.subTest(cle=cle),self.assertRaises(ValueError):audit.verifier_reprise(rapport|{cle:valeur})

    def test_cadres_limitent_fichier_fonction_et_ligne_sans_fragment(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp);(source/'scripts').mkdir()
            p=source/'scripts'/audit.SCRIPTS[0]
            p.write_text('def worker():\n    raise ValueError("message privé")\n');p.chmod(0o600)
            prive='contenu-personnel-secret'
            trace=f'File "{p}", line 2, in worker\n{prive}\nFile "{p}", line 999, in worker\nFile "{p}", line 1, in {prive}\nFile "/autre/{prive}", line 1, in worker\n'
            r=audit.cadres(trace,source)
            self.assertEqual(r,[dict(script=audit.SCRIPTS[0],fonction='worker',ligne=2)])
            self.assertNotIn(prive,json.dumps(r));self.assertNotIn(str(source),json.dumps(r))
            p.chmod(0o666)
            with self.assertRaises(ValueError):audit.cadres(trace,source)
            p.chmod(0o600);autre=source/'original';p.rename(autre);p.symlink_to(autre)
            with self.assertRaises(OSError):audit.cadres(trace,source)

    def test_etats_unites_et_journaux_namespace_restent_fermes(self):
        secret=b'valeur-utilisateur-privee'
        reponses=[SimpleNamespace(stdout=b'ActiveState=inactive\nExecMainStatus=0\nResult='+secret+b'\n',returncode=0),
            SimpleNamespace(stdout=b'peer authentication failed '+secret,returncode=0)]*3
        with patch.object(audit.subprocess,'run',side_effect=reponses) as appels:
            r=audit.unites_identite(Path('/outils'))
            self.assertEqual(len(r),3)
            for v in r.values():self.assertEqual(v,dict(etat='inactive',code=0,resultat='indetermine',categories=['journal_pg_peer_refuse']))
            self.assertNotIn(secret.decode(),json.dumps(r))
            for a in appels.call_args_list[1::2]:self.assertIn('--namespace=identite',a.args[0])

    def test_lecture_refuse_liens_droits_taille_et_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'prive';p.write_text('texte');p.chmod(0o600)
            self.assertEqual(audit.lire(p),'texte')
            lien = Path(tmp)/'lien';lien.symlink_to(p)
            with self.assertRaises(OSError): audit.lire(lien)
            os.link(p,Path(tmp)/'dur')
            with self.assertRaises(ValueError): audit.lire(p)
            (Path(tmp)/'dur').unlink();p.chmod(0o644)
            with self.assertRaises(ValueError): audit.lire(p)
            p.chmod(0o600);p.write_bytes(b'x'*262145)
            with self.assertRaises(ValueError): audit.lire(p)
            fifo = Path(tmp)/'fifo';os.mkfifo(fifo,0o600)
            with self.assertRaises(ValueError): audit.lire(fifo)

    def test_plan_n_admet_aucun_parametre_ou_commande(self):
        for action in ('amorcage','diagnostic'):
            self.assertEqual(plan.verifier(dict(version=1,action=action)),action)
        for valeur in (dict(version=True,action='amorcage'),dict(version=1,action='shell'),
                dict(version=1,action='diagnostic',commande='libre'),dict(version=1,action='diagnostic\nautre=oui')):
            with self.assertRaises(ValueError):plan.verifier(valeur)


if __name__ == '__main__': unittest.main()
