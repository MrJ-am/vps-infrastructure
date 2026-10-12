import importlib.util
from pathlib import Path
import unittest
import json
import tempfile
from unittest.mock import patch
from types import SimpleNamespace

s=importlib.util.spec_from_file_location('diagnostic',Path(__file__).resolve().parents[1]/'scripts/monolithe-diagnostic.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)


class Diagnostic(unittest.TestCase):
    def test_locations_installees_metadata_uniquement(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);p=d/'payload/vps/assemblage';p.mkdir(parents=True)
            (p/'manifest.json').write_text('{"toolchain":{"production":{"nixpkgs":"/nix/store/nixpkgs"}}}')
            rows={'= /':{'existe':True,'root':True,'secret':'prive','alias':False,'directives':['try_files','secret']},
                  'inconnu':{'secret':'prive'}}
            with patch.object(m.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout=json.dumps(rows))) as run:
                r=m.locations_vision(d)
            self.assertEqual(r['= /'],{'existe':True,'root':True,'alias':False,'directives':['try_files']})
            self.assertNotIn('prive',json.dumps(r));self.assertNotIn('secret',json.dumps(r))
            self.assertIn('--eval',run.call_args.args[0]);self.assertNotIn('nix-build',run.call_args.args[0])
            with patch.object(m.subprocess,'run',return_value=SimpleNamespace(returncode=1,stdout='secret')):
                self.assertEqual(m.locations_vision(d),{'evaluation_code':1})

    def test_erreur_nix_ne_revele_pas_les_definitions_privees(self):
        t='error: The option `services.nginx.virtualHosts."vision.mrj.am".locations."= /".root` has conflicting definition values:\n- In /configuration-privee.nix: SECRET\nat /root/private/module.nix:34:5\n'
        r=m.erreur_nix(t)
        self.assertEqual(r['categories'],['definitions_conflictuelles'])
        self.assertEqual(r['options_routage'],['services.nginx.virtualHosts."vision.mrj.am".locations."= /".root'])
        self.assertEqual(r['positions'],[{'fichier':'module.nix','ligne':34,'colonne':5}])
        self.assertNotIn('SECRET',json.dumps(r));self.assertNotIn('private',json.dumps(r));self.assertNotIn('privee',json.dumps(r))
        self.assertNotIn('SECRET',json.dumps(m.erreur_nix('error: valeur `SECRET` non valide')))
        self.assertEqual(m.erreur_nix('Only one of nginx root or alias can be specified on a location.')['regle_nginx'],'root_alias_exclusifs')

    def test_nginx_binaire_fixe_sans_executer_la_configuration(self):
        b='/nix/store/'+'a'*32+'-nginx-1.30.4/bin/nginx'
        with patch.object(m.subprocess,'run',return_value=SimpleNamespace(stderr='nginx version: nginx/1.30.4\n')) as run,\
             patch.object(m.Path,'read_bytes',return_value=b'code'):
            r=m.version_nginx(b+' -c /configuration-privee')
        self.assertEqual(run.call_args.args[0],[b,'-v']);self.assertEqual(r['version'],'1.30.4')
        self.assertNotIn('privee',json.dumps(r))
        with self.assertRaises(ValueError):m.version_nginx('/usr/bin/nginx -c secret')
        with patch.object(m.subprocess,'run',return_value=SimpleNamespace(stderr='secret')):
            with self.assertRaisesRegex(ValueError,'hors format'):m.version_nginx(b)

    def test_sondes_fermees_sans_url_corps_ou_champ_libre(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);self.assertEqual(m.sondes_publiques(d),{})
            (d/'sondes-publiques.json').write_text(json.dumps({'matheval':{'codes':[200,429],'hors_contrat':True,'secret':'prive'},
                'inconnu':{'codes':[200]},'log':{'codes':['secret'],'disponibilite_codes':[503,200]}}))
            r=m.sondes_publiques(d)
        self.assertEqual(r,{'matheval':{'codes':[200,429],'hors_contrat':True},'log':{'disponibilite_codes':[503,200]}})
        self.assertNotIn('prive',json.dumps(r));self.assertNotIn('secret',json.dumps(r))

    def test_etat_bascule_ferme_ne_revele_pas_le_plan_prive(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp)
            self.assertEqual(m.etat_bascule(d),{'phase_activation':'absente-ou-inconnue',
                'retour_code_enregistre':False,'qualification_finale_enregistree':False})
            (d/'activation.json').write_text(json.dumps({'phase':'anciens-arretes','etats':{'prive':'secret'}}))
            (d/'retour.json').write_text('{}')
            r=m.etat_bascule(d)
            self.assertEqual(r['phase_activation'],'anciens-arretes')
            self.assertTrue(r['retour_code_enregistre']);self.assertFalse(r['qualification_finale_enregistree'])
            self.assertNotIn('secret',json.dumps(r))
            (d/'activation.json').write_text('{"phase":"secret"}')
            self.assertNotIn('secret',json.dumps(m.etat_bascule(d)))

    def test_traversee_exacte_sous_vision_sans_lire_de_fichier(self):
        for code in (0,1):
            with patch.object(m.subprocess,'run',return_value=SimpleNamespace(returncode=code)) as run:
                self.assertEqual(m.acces_parent_restauration(),code==0)
                self.assertEqual(run.call_args.args[0],['runuser','-u','vision','--','test','-x','/var/lib/postgresql'])
        with patch.object(m.subprocess,'run',return_value=SimpleNamespace(returncode=2)):
            with self.assertRaisesRegex(ValueError,'indisponible'):m.acces_parent_restauration()

    def test_unit_values_are_never_emitted(self):
        a={'units':{'auth':'ExecStart=ancien\nEnvironment=SECRET=prive-a\nUser=auth'}}
        b={'units':{'auth':'ExecStart=nouveau\nEnvironment=SECRET=prive-b\nUser=auth'}}
        r=m.differences(a,b)
        self.assertEqual(r[0]['proprietes_modifiees'],['Environment','ExecStart'])
        self.assertNotIn('prive',json.dumps(r));self.assertNotIn('ancien',json.dumps(r))

    def test_identical_and_structured_changes(self):
        self.assertEqual(m.differences({'a':1},{'a':1}),[])
        self.assertEqual(m.differences({'postgres':{'package':'a'}},{'postgres':{'package':'b'}})[0]['champ'],'/postgres/package')

    def test_identmap_diagnostic_ne_revele_pas_les_valeurs_inconnues(self):
        a='map_prive compte_prive role_prive\n'
        b=a+'mrjam_metier mrjam-metier vision\n'
        r=m.diagnostic_identmap(a,b)
        self.assertTrue(r['ancien_prefixe_preserve'])
        self.assertEqual(r['positions_ajouts']['vision'],[1])
        self.assertFalse(r['seuls_ajouts_attendus'])
        self.assertNotIn('prive',json.dumps(r))

    def test_identmap_compte_les_champs_et_les_doublons(self):
        r=m.diagnostic_identmap('m u r','m u rmrjam_metier mrjam-metier vision\nmrjam_metier mrjam-metier vision')
        self.assertEqual(r['nombre_colonnes_apres'],[5,3])
        self.assertFalse(r['ancien_prefixe_preserve'])
        self.assertEqual(r['positions_ajouts']['vision'],[1])

    def test_condition_privee_ne_revele_ni_message_ni_ligne_source(self):
        t='Traceback (most recent call last):\n  File "/root/prive/script.py", line 42, in qualifier\n    contenu_personnel = secret\nValueError: contenu_personnel et secret'
        r=m.diagnostic_erreur(t)
        self.assertEqual(r,{'exception':'ValueError','pile':[{'fichier':'script.py','ligne':42}]})
        self.assertNotIn('secret',json.dumps(r))
        self.assertNotIn('prive',json.dumps(r))

    def test_role_privilegie_seulement_si_exact_et_versionne(self):
        t='ValueError: Rôle SQL privilégié : vision'
        self.assertEqual(m.diagnostic_erreur(t,(),{'vision'})['role_sql_privilegie'],'vision')
        self.assertNotIn('role_sql_privilegie',m.diagnostic_erreur(t,(),{'autre'}))
        self.assertNotIn('role_sql_privilegie',m.diagnostic_erreur(t+' secret',(),{'vision'}))

    def test_roles_metadonnees_lecture_seule_filtrees(self):
        champs=('super','bypass','creer_role','creer_base','replication','membre_proprietaire')
        rows=[{'nom':r,**{k:False for k in champs},'secret':'prive'} for r in ('vision','inconnu')]
        with patch.object(m.subprocess,'run',return_value=SimpleNamespace(stdout=json.dumps(rows))) as run:
            r=m.metadonnees_roles('/nix/store/postgres','vision',{'vision'},SimpleNamespace(ROLES_SQL='SELECT {roles}'))
        self.assertEqual(set(r),{'vision'});self.assertNotIn('prive',json.dumps(r))
        self.assertIn('BEGIN READ ONLY',run.call_args.kwargs['input'])
        with self.assertRaises(ValueError):m.metadonnees_roles('/nix/store/postgres','autre',{'vision'},None)
        with self.assertRaises(ValueError):m.metadonnees_roles('/nix/store/postgres','vision',{'secret;'},None)

    def test_vue_historique_metadonnees_seules(self):
        r={'existe':True,'proprietaire_vision':True,'proprietaire_migration':False,'secret':'prive'}
        with patch.object(m.subprocess,'run',return_value=SimpleNamespace(stdout=json.dumps(r))) as run:
            v=m.proprietes_vue_historique('/nix/store/postgres')
        self.assertNotIn('secret',v)
        self.assertIn('BEGIN READ ONLY',run.call_args.kwargs['input'])
        self.assertNotIn('FROM vision_browser_sheets',run.call_args.kwargs['input'])

    def test_seul_champ_de_contrat_de_table_versionnee_est_emis(self):
        t='ValueError: Contrat SQL divergent : public.vision_items force_rls'
        r=m.diagnostic_erreur(t,{'public.vision_items'})
        self.assertEqual(r['contrat_sql'],{'table':'public.vision_items','champ':'force_rls'})
        self.assertNotIn('contrat_sql',m.diagnostic_erreur(t,{'public.autre'}))
        self.assertNotIn('contrat_sql',m.diagnostic_erreur(t+' contenu_prive',{'public.vision_items'}))

    def test_metadonnees_uniquement_et_tables_versionnees(self):
        rows=[{'table':t,'rls':True,'force_rls':True,'colonne_utilisateur':True,'politiques':1}
              for t in ('public.vision_contextes','public.inconnue_privee')]
        with patch.object(m.subprocess,'run',return_value=SimpleNamespace(stdout=json.dumps(rows))) as run:
            r=m.metadonnees_rls('/nix/store/postgres','vision',{'public.vision_contextes'})
        self.assertEqual(set(r),{'public.vision_contextes'})
        self.assertIn('BEGIN READ ONLY',run.call_args.kwargs['input'])
        self.assertNotIn('FROM public.',run.call_args.kwargs['input'])
        with self.assertRaises(ValueError):m.metadonnees_rls('/nix/store/postgres','autre',{})


if __name__=='__main__':unittest.main()
