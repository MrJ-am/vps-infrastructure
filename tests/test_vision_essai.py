"""Récupération exigée, artefact fermé et simulation sans unité étrangère."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('essai_qualification',ROOT/'scripts/vision-essai-qualification.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)


class Essai(unittest.TestCase):
    def test_preuve_complete_exterieure_necessaire(self):
        r=json.loads((ROOT/'operations/vision-recuperation-resultat.json').read_text())
        c=json.loads((ROOT/'operations/vision-recuperation-confirmation.json').read_text())
        m.verifier_recuperation(r,c)
        for cle,valeur in [('version',True),('dechiffrement_complet',False),('preuve_aleatoire_verifiee',False),
            ('copie_exterieure_verifiee',False),('preuve_sha256','a'*64),('cle_privee_transmise',True),
            ('chiffre_sha256','b'*64),('execution',38047719442),('cle_publique','age1autre')]:
            d=copy.deepcopy(c);d[cle]=valeur
            with self.subTest(cle=cle),self.assertRaises(ValueError):m.verifier_recuperation(r,d)

    def test_interface_exacte_et_corruption_refusee(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);r=m.extraire_interface(ROOT/'vendor/vision-multiutilisateur-interface.zip',d/'interface')
            self.assertEqual(len(r['fichiers']),22)
            with self.assertRaises(ValueError):m.extraire_interface(ROOT/'vendor/vision-multiutilisateur-interface.zip',d/'interface')
            p=d/'autre.zip';p.write_bytes(b'archive incorrecte')
            with self.assertRaises(ValueError):m.extraire_interface(p,d/'autre')

    def test_dry_unite_etrangere_et_systemd_refuses(self):
        texte='would restart the following units: vision.service, mrj-auth.service\nwould activate the configuration'
        self.assertEqual(m.verifier_dry(texte),['mrj-auth.service','vision.service'])
        for t in (texte.replace('vision.service','matheval.service'),texte.replace('vision.service','sshd.service'),
            texte+'\nwould restart systemd',texte+'\nwould start the following units: unite-etrangere.service',
            'would restart the following units: vision.service'):
            with self.assertRaises(ValueError):m.verifier_dry(t)

    def test_retour_shell_autonome_syntaxe(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'retour.sh';p.write_text(m.script_retour(Path('/root/vision-bascule-preparations')/('a'*40),
                '/nix/store/'+('b'*32)+'-nixos-system-test',Path('/nix/store/'+('b'*32)+'-nixos-system-test/sw/bin'),
                Path('/nix/store/'+('c'*32)+'-postgresql-17.11'),Path('/nix/store/'+('d'*32)+'-util-linux/bin/runuser'),
                'vision-essai-aaaaaaaaaaaa.service'))
            subprocess.run(['bash','-n',str(p)],check=True)

    def test_repertoires_exigent_profil_complet_sans_perte(self):
        r=dict(resetup_identique_hors_triggers=True,regles_existantes_hors_perimetre_identiques=True,
            lien_import_keycloak_nouveau_exact=True,fichiers_tmpfiles_ajoutes=['10-keycloak.conf'],
            fichiers_tmpfiles_retires=[],regles_connues={'sauvegarde_amorcage':dict(avant=1,apres=1),
                'sauvegarde_commune':dict(avant=0,apres=1),'effacements_vision':dict(avant=0,apres=1)})
        self.assertTrue(m.verifier_repertoires(r))
        for k,v in [('resetup_identique_hors_triggers',False),('regles_existantes_hors_perimetre_identiques',False),
            ('lien_import_keycloak_nouveau_exact',False),('fichiers_tmpfiles_ajoutes',['10-keycloak.conf','autre.conf']),
            ('fichiers_tmpfiles_retires',['ancien.conf'])]:
            d=copy.deepcopy(r);d[k]=v
            with self.subTest(k=k),self.assertRaises(ValueError):m.verifier_repertoires(d)
        for valeur in (0,2,True):
            d=copy.deepcopy(r);d['regles_connues']['sauvegarde_amorcage']['apres']=valeur
            with self.assertRaises(ValueError):m.verifier_repertoires(d)

    def test_arret_demarrage_tmpfiles_seulement_apres_preuve_et_bus_refuse(self):
        t='would stop the following units: systemd-tmpfiles-resetup.service\nwould start the following units: systemd-tmpfiles-resetup.service\nwould activate the configuration'
        with self.assertRaises(ValueError):m.verifier_dry(t)
        self.assertEqual(m.verifier_dry(t,True),['systemd-tmpfiles-resetup.service'])
        self.assertEqual(m.verifier_dry('\x1b[32m'+t+'\x1b[0m',True),['systemd-tmpfiles-resetup.service'])
        for texte in (t.replace('would start','would reload'),t.replace('would start','would restart'),
            t+'\nwould reload the following units: dbus-broker.service',t+'\nwould stop the following units: sshd.service'):
            with self.assertRaises(ValueError):m.verifier_dry(texte,True)


if __name__=='__main__':unittest.main()
