"""Retour du code avec derniers états, refus et reprise ; aucun VPS contacté."""
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('activer_monolithe',ROOT/'scripts/monolithe-activer.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)


class Retour(unittest.TestCase):
    def test_parent_ressources_publiques_corrige_sans_ouvrir_bundle_prive(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=Path(tmp);parent=r/'public';parent.mkdir(mode=0o700)
            public=parent/('a'*40);public.mkdir(mode=0o700)
            f=public/'app.html';f.write_text('document synthétique');f.chmod(0o600)
            prive=r/'prive';prive.mkdir(mode=0o700)
            with patch.object(m.stage,'PUBLICATION_ROOT',parent):
                m.stage.permissions_ressources(public);m.stage.permissions_ressources(public)
                with self.assertRaisesRegex(ValueError,'hors périmètre'):m.stage.permissions_ressources(prive)
            self.assertEqual(parent.stat().st_mode & 0o777,0o755)
            self.assertEqual(f.stat().st_mode & 0o777,0o644)
            self.assertEqual(f.read_text(),'document synthétique')
            self.assertEqual(prive.stat().st_mode & 0o777,0o700)

    def test_lien_ressource_refuse_avant_elargissement_du_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=Path(tmp);parent=r/'public';parent.mkdir(mode=0o700)
            public=parent/('a'*40);public.mkdir();(public/'lien').symlink_to(r/'secret')
            with patch.object(m.stage,'PUBLICATION_ROOT',parent):
                with self.assertRaisesRegex(ValueError,'Lien'):m.stage.permissions_ressources(public)
            self.assertEqual(parent.stat().st_mode & 0o777,0o700)

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.r=Path(self.tmp.name)
        self.d=self.r/('a'*40);self.d.mkdir(mode=0o700)
        self.current=self.r/'commun';self.current.mkdir(mode=0o700)
        self.old=self.r/'historique';self.old.mkdir(mode=0o700)
        self.source=self.current/'courriel/file.sqlite';self.source.parent.mkdir(mode=0o700)
        self.target=self.old/'file.sqlite'
        for p,rows in [(self.source,[(1,b'\x00\xff',0),(2,b'apres-bascule',None)]),(self.target,[(1,b'ancien',0)])]:
            with sqlite3.connect(p) as c:
                c.execute('CREATE TABLE courriels(id int PRIMARY KEY,message BLOB,accepte int)')
                c.executemany('INSERT INTO courriels VALUES(?,?,?)',rows)
            p.chmod(0o600)
        self.plan={'phase':'service-demarre','etats':{'courriel':m.proprietes(self.target)},'unites_avant':{'vision':'active','matheval':'active'}}
        self.before={'generation':'/nix/store/ancien','configuration_cible':'/config-original',
                     'configuration_lien':'/config-original'}
        self.prepare={'avant':self.before};self.appels=[]

    def lancer(self):
        with patch.object(m,'ETAT_METIER',self.current),patch.object(m,'PORTE',self.r/'porte'),\
             patch.object(m.stage,'ETATS',{'courriel':str(self.target)}),\
             patch.object(m.stage,'commande',side_effect=lambda a,d:self.appels.append([str(v) for v in a]) or b''),\
             patch.object(m.stage,'etat',return_value=self.before),patch.object(m,'changer_configuration'):
            m.retour(self.d,self.prepare,self.plan)

    def test_roles_transmis_par_stdin_sans_ouvrir_le_bundle_a_postgres(self):
        with patch.object(m.stage,'commande') as commande:
            m.appliquer_roles(Path('/nix/store/postgresql/bin'),self.d)
        args=commande.call_args.args[0]
        self.assertEqual(args[:4],['runuser','-u','postgres','--'])
        self.assertIn('--file=-',args)
        self.assertIn('--host=/run/postgresql',args)
        self.assertIn('--dbname=vision',args)
        self.assertNotIn(ROOT/'assemblage/roles-metier.sql',args)
        self.assertEqual(commande.call_args.kwargs['input'],(ROOT/'assemblage/roles-metier.sql').read_bytes())
        self.assertTrue(commande.call_args.kwargs['input'].startswith(b'-- Installation explicite'))

    def test_lanceur_transitoire_ne_remplace_pas_la_verification_du_binaire(self):
        with patch.object(m.stage,'commande',return_value=b'123\n'),\
             patch.object(m.stage,'sha',side_effect=['b'*64,'a'*64]),patch.object(m.time,'sleep') as pause:
            self.assertEqual(m.attendre_artefact(self.d,'a'*64),'123')
            pause.assert_called_once_with(.05)
        self.assertEqual(json.loads((self.d/'artefact-servi.json').read_text())['artefact_constate_sha256'],'a'*64)

    def test_mauvais_binaire_persistant_et_pid_absent_restent_refuses(self):
        for pid in (b'123\n',b'0\n'):
            with self.subTest(pid=pid),patch.object(m.stage,'commande',return_value=pid),\
                 patch.object(m.stage,'sha',return_value='b'*64),patch.object(m.time,'monotonic',side_effect=[0,10]):
                with self.assertRaisesRegex(ValueError,'après attente bornée'):m.attendre_artefact(self.d,'a'*64)

    def test_reprise_exige_retour_et_configuration_identiques(self):
        ancien=self.r/('b'*40);ancien.mkdir()
        (ancien/'preparation.json').write_text(json.dumps({'avant':self.before}))
        preuve={'revision':'b'*40,'retour_code':True,'restauration_ancienne_sql':False,'derniers_etats_durables_recopies':True}
        (ancien/'retour.json').write_text(json.dumps(preuve))
        cert={'manifest':{'qualification':{'retour_precedent':'b'*40}}}
        with patch.object(m,'ETAT_METIER',self.current),patch.object(m.stage,'commande',return_value=b'0'):
            self.assertTrue(m.reprise_certifiee(self.d,self.prepare,cert))
            preuve['derniers_etats_durables_recopies']=False
            (ancien/'retour.json').write_text(json.dumps(preuve))
            with self.assertRaisesRegex(ValueError,'non établi'):m.reprise_certifiee(self.d,self.prepare,cert)
        self.assertFalse(m.reprise_certifiee(self.d,self.prepare,{'manifest':{'qualification':{}}}))

    def test_reprise_priorite_aux_ecritures_historiques_et_conservation_etat_nouveau(self):
        absent=self.old/'nouveau.sqlite'
        with patch.object(m,'ETAT_METIER',self.current),patch.object(m.stage,'ETATS',{'courriel':str(self.target),'admissions':str(absent)}):
            sources=m.sources_durables(True)
            self.assertEqual(sources['courriel'],self.target)
            self.assertEqual(sources['admissions'],self.current/'admission/admissions.sqlite')
            self.assertEqual(m.sources_durables(False)['admissions'],absent)

    def test_retour_partiel_ne_recopie_pas_sur_ecriture_historique_recente(self):
        self.plan['etats_retour_copies']=True
        with sqlite3.connect(self.target) as c:c.execute("INSERT INTO courriels VALUES(3,X'01',1)")
        self.lancer()
        with sqlite3.connect(self.target) as c:self.assertEqual(c.execute('SELECT * FROM courriels ORDER BY id').fetchall(),[(1,b'ancien',0),(3,b'\x01',1)])

    def test_retour_enregistre_la_relance_tiers_sans_affaiblir_le_controle_de_bascule(self):
        self.before['tiers_pids']={'keycloak':'1'}
        actuel=dict(self.before,tiers_pids={'keycloak':'2'})
        with patch.object(m.stage,'etat',return_value=actuel),patch.object(m.stage,'commande'):
            self.assertEqual(m.metadonnees_retour_identiques(self.d,self.prepare),['keycloak'])
        actuel['configuration_cible']='autre'
        with patch.object(m.stage,'etat',return_value=actuel),patch.object(m.stage,'commande'):
            with self.assertRaisesRegex(ValueError,'Configuration différente'):m.metadonnees_retour_identiques(self.d,self.prepare)

    def test_retour_conserve_ecritures_posterieures_et_ne_restaure_pas_sql(self):
        self.lancer()
        with sqlite3.connect(self.target) as c:
            self.assertEqual(c.execute('SELECT * FROM courriels ORDER BY id').fetchall(),[(1,b'\x00\xff',0),(2,b'apres-bascule',None)])
        self.assertFalse(any('pg_restore' in ' '.join(a) or 'pg_dump' in ' '.join(a) for a in self.appels))
        self.assertTrue(json.loads((self.d/'retour.json').read_text())['derniers_etats_durables_recopies'])

    def test_reprise_retour_necrase_pas_une_ecriture_historique_recente(self):
        self.lancer()
        with sqlite3.connect(self.target) as c:c.execute("INSERT INTO courriels VALUES(3,X'01',1)")
        self.lancer()
        with sqlite3.connect(self.target) as c:self.assertEqual(c.execute('SELECT count(*) FROM courriels').fetchone(),(3,))

    def test_cible_redirigee_et_copie_concurrente_refusees(self):
        self.target.unlink();self.target.symlink_to(self.source)
        with self.assertRaisesRegex(ValueError,'redirigée'):self.lancer()
        self.assertFalse((self.d/'retour.json').exists())
        self.target.unlink();self.target.with_name(self.target.name+'.assemblage-copie').write_text('concurrent')
        with self.assertRaisesRegex(ValueError,'concurrente'):self.lancer()

    def test_avant_transfert_ne_reinjecte_pas_d_etat(self):
        self.plan['phase']='anciens-arretes';self.lancer()
        with sqlite3.connect(self.target) as c:self.assertEqual(c.execute('SELECT message FROM courriels').fetchone(),(b'ancien',))

    def test_retour_avant_creation_de_l_unite_commune(self):
        self.plan['phase']='anciens-arretes'
        def commande(a,d):
            self.appels.append([str(v) for v in a])
            return b'not-found\n' if 'LoadState' in a else b''
        with patch.object(m.stage,'commande',side_effect=commande),patch.object(m.stage,'etat',return_value=self.before),\
             patch.object(m,'changer_configuration'),patch.object(m,'PORTE',self.r/'porte'):
            m.retour(self.d,self.prepare,self.plan)
        self.assertNotIn(['systemctl','stop','mrjam-metier'],self.appels)
        self.assertTrue((self.d/'retour.json').exists())

    def test_retour_reste_utilisable_apres_validation(self):
        (self.d/'termine.json').write_text('{"validation":true}')
        self.lancer();self.assertTrue((self.d/'retour.json').exists());self.assertTrue((self.d/'termine.json').exists())

    def test_bascule_refuse_une_restauration_sans_reconciliation_rls(self):
        for preuve in (None,False,'true'):
            with self.subTest(preuve=preuve):
                (self.d/'restauration.json').write_text(json.dumps({'qualification_applicative':{
                    'migration_27_rls_sur_copie':preuve}}))
                with patch.object(m.stage,'etat',return_value=self.before),patch.object(m.stage,'commande') as commande:
                    with self.assertRaisesRegex(ValueError,'Réconciliation RLS non qualifiée'):
                        m.activer(self.d,self.prepare,{})
                    commande.assert_not_called()
                self.assertFalse((self.d/'activation.json').exists())

    def test_bascule_refuse_une_restauration_sans_preuve_temporelle(self):
        (self.d/'restauration.json').write_text(json.dumps({'qualification_applicative':{
            'migration_27_rls_sur_copie':True}}))
        with patch.object(m.stage,'etat',return_value=self.before),patch.object(m.stage,'commande') as commande:
            with self.assertRaisesRegex(ValueError,'Fenêtres temporelles non qualifiées'):
                m.activer(self.d,self.prepare,{})
            commande.assert_not_called()
        self.assertFalse((self.d/'activation.json').exists())


if __name__=='__main__':unittest.main()
