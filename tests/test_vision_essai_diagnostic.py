"""Aucun nom d'unité libre, identité, chemin ou journal brut exporté."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

s=importlib.util.spec_from_file_location('essai_diagnostic',Path(__file__).resolve().parents[1]/'scripts/vision-essai-diagnostiquer.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)


class Diagnostic(unittest.TestCase):
    def test_observateur_texte_utf8_exact_et_corruption_refusee(self):
        texte=(Path(__file__).resolve().parents[1]/'scripts/vision-proprietaire-enroler.py').read_text()
        m.verifier_observateur(texte)
        with self.assertRaises(ValueError):m.verifier_observateur(texte+'\n')

    def test_action_concrete_connue_et_triggers(self):
        r=m.classer('would stop the following units: systemd-tmpfiles-resetup.service\nwould activate the configuration')
        self.assertEqual(r['actions_connues'],[dict(action='stop',unite='systemd-tmpfiles-resetup.service')])
        self.assertTrue(r['activation_simulee']);self.assertFalse(r['redemarrage_systemd_annonce'])

    def test_inconnu_et_journal_prive_non_exportes(self):
        r=m.classer('secret@example.test /root/contenu\nwould restart the following units: mot-secret.service, matheval.service')
        self.assertEqual(r['unites_inconnues'],1)
        self.assertEqual(r['actions_connues'],[dict(action='restart',unite='matheval.service')])
        self.assertNotIn('secret',json.dumps(r));self.assertNotIn('/root',json.dumps(r))

    def test_regles_reservees_et_changement_etranger(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Path(tmp);ancien,nouveau=store/'ancien',store/'nouveau'
            for p,triggers in ((ancien,'avant'),(nouveau,'apres')):
                (p/'etc/systemd/system').mkdir(parents=True)
                (p/'etc/tmpfiles.d').mkdir(parents=True)
                (p/'etc/systemd/system/systemd-tmpfiles-resetup.service').write_text(
                    '[Unit]\nX-Restart-Triggers='+triggers+'\n[Service]\nExecStart=/outil --create\n')
            fichier='nixos.conf';ancien_regle='d /var/backup/mrjam-amorcage 0700 root root -'
            ancienne='d /var/lib/service-secret 0700 root root -\n'+ancien_regle+'\n'
            (ancien/'etc/tmpfiles.d'/fichier).write_text(ancienne)
            (nouveau/'etc/tmpfiles.d'/fichier).write_text(ancienne+
                'd /var/backup/mrjam 0700 root root -\nd /var/lib/vision-effacements 0700 vision vision -\n')
            r=m.comparer_repertoires(ancien,nouveau,store)
            self.assertTrue(r['resetup_identique_hors_triggers']);self.assertTrue(r['regles_hors_perimetre_identiques'])
            self.assertEqual(r['regles_connues']['sauvegarde_amorcage'],dict(avant=1,apres=1))
            self.assertNotIn('secret',json.dumps(r));self.assertNotIn(tmp,json.dumps(r))
            p=nouveau/'etc/tmpfiles.d'/fichier;p.write_text(p.read_text().replace('0700 root','0777 root'))
            self.assertFalse(m.comparer_repertoires(ancien,nouveau,store)['regles_hors_perimetre_identiques'])
            p=nouveau/'etc/systemd/system/systemd-tmpfiles-resetup.service'
            p.write_text(p.read_text().replace('--create','--remove'))
            self.assertFalse(m.comparer_repertoires(ancien,nouveau,store)['resetup_identique_hors_triggers'])

    def test_etape_arbitraire_refusee(self):
        with self.assertRaises(ValueError):m.etape('secret@example.test')
        self.assertIn(m.ETAPE,m.ETAPES)

    def test_reactivation_sysinit_connue_sans_nom_arbitraire(self):
        r=m.classer('would start the following units: sysinit-reactivation.target, userborn.service, secret.target')
        self.assertEqual(r['actions_connues'],[dict(action='start',unite='sysinit-reactivation.target'),
            dict(action='start',unite='userborn.service')])
        self.assertEqual(r['unites_inconnues'],1)
        self.assertNotIn('secret',json.dumps(r))

    def test_refus_ne_publie_ni_exception_privee_ni_cadre_externe(self):
        try:raise FileNotFoundError('/root/secret@example.test')
        except Exception as e:r=m.refus_ferme(e)
        self.assertEqual(r['exception_connue'],'FileNotFoundError')
        self.assertEqual(r['cadres_lecteur'],[])
        self.assertNotIn('secret',json.dumps(r));self.assertNotIn('/root',json.dumps(r))
        try:m.exiger(False)
        except Exception as e:r=m.refus_ferme(e)
        self.assertEqual(r['cadres_lecteur'],[dict(ligne=m.exiger.__code__.co_firstlineno+1,fonction='exiger')])

    def test_unite_native_sans_contenu_ni_instance_nominative(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);store=d/'store';s=store/'generation';u=s/'etc/systemd/system';u.mkdir(parents=True)
            (u/'opaque-native.service').write_text('contenu-prive@exemple.test')
            (u/'personne@exemple.test.service').write_text('identite')
            prive=d/'externe.service';prive.write_text('secret');(u/'externe.service').symlink_to(prive)
            connus=m.unites_publiques((s,),store)
            self.assertEqual(connus,{'opaque-native.service'})
            r=m.classer('would stop the following units: opaque-native.service, secret.service',connus)
            self.assertEqual(r['actions_connues'],[dict(action='stop',unite='opaque-native.service',source_unite_generee=True)])
            self.assertEqual(r['unites_inconnues'],1);self.assertEqual(r['unites_rattachees_source_generee'],1)
            for valeur in ('contenu-prive','personne@','externe','secret.service'):self.assertNotIn(valeur,json.dumps(r))

    def test_montage_credential_a_nom_constant(self):
        unite=r'run-credentials-mrjam\x2damorcage\x2didentite.service.mount'
        r=m.classer('would stop the following units: '+unite)
        self.assertEqual(r['actions_connues'],[dict(action='stop',unite=unite)])
        self.assertEqual(r['unites_inconnues'],0)

    def test_seul_nouveau_lien_import_keycloak_identifie(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Path(tmp);a,n=store/'ancien',store/'nouveau'
            for p in (a,n):
                (p/'etc/systemd/system').mkdir(parents=True);(p/'etc/tmpfiles.d').mkdir(parents=True)
                (p/'etc/systemd/system/systemd-tmpfiles-resetup.service').write_text('[Unit]\nX-Restart-Triggers=fixe\n')
                (p/'etc/tmpfiles.d/nixos.conf').write_text('d /var/lib/autre 0700 root root -\n')
            lien=n/'etc/tmpfiles.d/10-keycloak.conf'
            lien.write_text('L+ /run/keycloak/data/import/realm-import.json - - - - /run/credentials/keycloak.service/realm-import\n')
            r=m.comparer_repertoires(a,n,store)
            self.assertTrue(r['lien_import_keycloak_nouveau_exact']);self.assertTrue(r['regles_existantes_hors_perimetre_identiques'])
            self.assertEqual(r['fichiers_tmpfiles_ajoutes'],['10-keycloak.conf'])
            ligne=lien.read_text();lien.write_text(' '.join("'"+champ+"'" for champ in ligne.split())+'\n')
            self.assertTrue(m.comparer_repertoires(a,n,store)['lien_import_keycloak_nouveau_exact'])
            lien.write_text(ligne.replace('/run/credentials/keycloak.service/realm-import','$(commande-interdite)'))
            self.assertFalse(m.comparer_repertoires(a,n,store)['lien_import_keycloak_nouveau_exact'])
            lien.write_text(ligne)
            lien.write_text(lien.read_text().replace('keycloak.service','secret-autre.service'))
            r=m.comparer_repertoires(a,n,store)
            self.assertFalse(r['lien_import_keycloak_nouveau_exact']);self.assertNotIn('secret',json.dumps(r))
