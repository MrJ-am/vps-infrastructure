"""Un seul propriétaire, aucun hash/identifiant public et preuves fermées."""
import copy
import contextlib
import io
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def charger(nom, fichier):
    spec = importlib.util.spec_from_file_location(nom, ROOT / 'scripts' / fichier)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


p = charger('proprietaire_test', 'vision-proprietaire.py')
a = charger('amorcage_test', 'vision-identite-amorcage-preparer.py')


class Proprietaire(unittest.TestCase):
    def test_refus_ne_projette_ni_message_ni_chemin_prive(self):
        texte = "FileNotFoundError: [Errno 2] secret_contact@exemple.test /root/prive\n"
        r = a.classer_refus(texte)
        self.assertEqual(r['exceptions'], ['FileNotFoundError'])
        self.assertNotIn('secret_contact', json.dumps(r))
        self.assertNotIn('/root/prive', json.dumps(r))

    def resume_nginx(self):
        paquet='/nix/store/'+'a'*32+'-nginx'
        return dict(nginx_paquet=paquet,nginx_commande=paquet+'/bin/nginx -c /nix/store/'+'b'*32+'-nginx.conf',
            systeme_actif='/nix/store/'+'c'*32+'-systeme',nginx_uid=60,nginx_gid=60,
            nginx_confinement=dict(User='nginx',Group='nginx',
                AmbientCapabilities=['CAP_NET_BIND_SERVICE','CAP_SYS_RESOURCE'],
                CapabilityBoundingSet=['CAP_NET_BIND_SERVICE','CAP_SYS_RESOURCE'],NoNewPrivileges=True))

    def test_nginx_isole_sous_uid_sans_capacite_supplementaire(self):
        r=self.resume_nginx();c=a.commande_nginx_isolee(r,'d'*40)
        self.assertIn('--property=User=nginx',c)
        self.assertIn('--property=Group=nginx',c)
        self.assertIn('--property=PrivateNetwork=yes',c)
        self.assertIn('--property=NoNewPrivileges=yes',c)
        self.assertIn('--property=CapabilityBoundingSet=CAP_NET_BIND_SERVICE',c)
        self.assertEqual(c[-6:],[r['nginx_paquet']+'/bin/nginx','-t','-e','stderr','-c','/nix/store/'+'b'*32+'-nginx.conf'])
        self.assertNotIn('CAP_SYS_RESOURCE',' '.join(c))
        self.assertIn('--property=TemporaryFileSystem=/run/nginx:rw,mode=0750,uid=60,gid=60 '
            '/var/cache/nginx:rw,mode=0750,uid=60,gid=60 /var/log/nginx:rw,mode=0750,uid=60,gid=60',c)

    def test_confinement_different_et_revision_libre_refuses(self):
        r=self.resume_nginx()
        for cle,valeur in (('User','root'),('Group','root'),('NoNewPrivileges',False),
                ('AmbientCapabilities',['CAP_SYS_ADMIN']),('CapabilityBoundingSet',['CAP_SYS_ADMIN'])):
            f=copy.deepcopy(r);f['nginx_confinement'][cle]=valeur
            with self.subTest(cle=cle),self.assertRaises(RuntimeError):a.commande_nginx_isolee(f,'d'*40)
        with self.assertRaises(RuntimeError):a.commande_nginx_isolee(r,'revision; id')
        for valeur in (0,False,-1,'60',65536):
            with self.subTest(uid=valeur),self.assertRaises(RuntimeError):
                a.commande_nginx_isolee({**r,'nginx_uid':valeur},'d'*40)

    def test_diagnostic_pid_nginx_sans_chemin_ou_message_prive(self):
        r=a.classer_refus('open() "/run/nginx/nginx.pid" failed (30: Read-only file system) secret_contact@exemple.test')
        self.assertEqual(r['nginx']['types_chemins'],['pid_nginx'])
        self.assertEqual(r['nginx']['errno'],[30])
        self.assertNotIn('secret_contact',json.dumps(r))
        self.assertNotIn('/run/nginx',json.dumps(r))

    def test_erreur_native_en_clair_reste_privee(self):
        sortie=io.StringIO();prive=b'secret_contact@exemple.test permission denied'
        with patch.object(a.subprocess,'run') as executer, \
                patch.object(a.construction.preparation,'diagnostic_prive') as garder, \
                contextlib.redirect_stdout(sortie):
            executer.return_value.returncode=1;executer.return_value.stderr=prive
            with self.assertRaises(a.construction.ConstructionRefusee):a.verifier_nginx(self.resume_nginx(),'d'*40)
            self.assertIn(prive,garder.call_args.args[0])
        self.assertNotIn('secret_contact',sortie.getvalue())
        self.assertEqual(json.loads(sortie.getvalue())['nginx_native'],'refuse')

    def test_commande_nginx_immuable_sans_option_ou_commande_libre(self):
        paquet='/nix/store/'+'a'*32+'-nginx-1.28.2'
        configuration='/nix/store/'+'b'*32+'-nginx.conf'
        r=dict(nginx_paquet=paquet,nginx_commande=paquet+"/bin/nginx -c '"+configuration+"'")
        self.assertEqual(a.commande_nginx(r),(paquet+'/bin/nginx',configuration))
        for commande in (r['nginx_commande']+' -g daemon=off',paquet+'/bin/nginx -c /etc/nginx/nginx.conf',
                paquet+'/bin/nginx -c '+configuration+'; id', '/tmp/nginx -c '+configuration):
            with self.subTest(commande=commande),self.assertRaises(RuntimeError):a.commande_nginx({**r,'nginx_commande':commande})

    def requete(self, contenu):
        def executer(q):
            if 'information_schema.columns' in q: return json.dumps(list(contenu))
            return json.dumps(next(v for k, v in contenu.items() if '"' + k + '"' in q))
        return executer

    def test_identifiant_unique_et_rapport_public_sans_identifiant(self):
        r = p.inspecter(self.requete({'vision_profils': ['prive'], 'vision_items': ['prive'],
            'vision_fiches': []}), ['prive'])
        self.assertEqual(r['utilisateur_historique'], 'prive')
        self.assertEqual(p.public(r), dict(proprietaires=1, tables_personnelles=3, authentification_unique=True))
        self.assertNotIn('prive', json.dumps(p.public(r)))

    def test_second_proprietaire_ou_compte_discordant_refuses(self):
        for contenu, comptes in (({'vision_profils': ['prive'], 'vision_items': ['autre']}, ['prive']),
            ({'vision_profils': ['prive', 'autre']}, ['prive']),
            ({'vision_profils': []}, ['prive']), ({'vision_profils': ['prive']}, ['autre']),
            ({'vision_profils': ['prive']}, ['prive', 'autre'])):
            with self.subTest(contenu=contenu, comptes=comptes), self.assertRaises(ValueError):
                p.inspecter(self.requete(contenu), comptes)

    def test_nom_de_table_injecte_et_identifiant_null_refuses(self):
        for c in ({'vision_profils': ['prive'], 'vision_items"; SELECT contenu': []},
                  {'vision_profils': ['prive'], 'vision_items': [None]},
                  {'vision_items': ['prive']}):
            with self.assertRaises(ValueError): p.inspecter(self.requete(c), ['prive'])

    def test_auth_unique_hash_prive_et_fichiers_non_conformes_refuses(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'htpasswd'
            texte = 'prive:$6$salt$' + 'a' * 86 + '\nvision-disabled:!\n'
            path.write_text(texte); path.chmod(0o600)
            self.assertEqual(p.identifiants_auth(path, os.geteuid(), os.getegid()), ['prive'])
            for suffixe in ('autre:$6$salt$' + 'b' * 86 + '\n', 'prive:!\n', 'invalide:secret_synthetique\n'):
                path.write_text(texte + suffixe)
                with self.assertRaises(ValueError): p.identifiants_auth(path, os.geteuid(), os.getegid())
            path.write_text(texte)
            path.chmod(0o644)
            with self.assertRaises(ValueError): p.identifiants_auth(path, os.geteuid(), os.getegid())
            path.chmod(0o600)
            lien = Path(d) / 'lien'; lien.symlink_to(path)
            with self.assertRaises(OSError): p.identifiants_auth(lien, os.geteuid(), os.getegid())
            lien.unlink(); os.link(path, lien)
            with self.assertRaises(ValueError): p.identifiants_auth(path, os.geteuid(), os.getegid())

    def test_preuve_composants_reelle_et_divergences_refusees(self):
        preuve = json.loads((ROOT / 'operations/vision-mrjam-composants-qualification.json').read_text())
        r = {k: v for k, v in preuve.items() if k not in
            ('run', 'job', 'socle_inchange', 'services_actifs', 'sondes_http_tls', 'nouvelle_connexion_ssh')}
        candidat = json.loads((ROOT / 'operations/vision-multiutilisateur-candidat.json').read_text())
        a.preuve_composants(r, preuve, candidat, preuve['paquet'])
        for cle in ('activation', 'inscriptions', 'identite_humaine', 'generation_constructible'):
            faux = {**r, cle: True}
            with self.subTest(cle=cle), self.assertRaises(a.construction.ConstructionRefusee):
                a.preuve_composants(faux, {**preuve, cle: True}, candidat, preuve['paquet'])
        with self.assertRaises(a.construction.ConstructionRefusee):
            a.preuve_composants(r, preuve, {**candidat, 'vision': '0' * 40}, preuve['paquet'])
        with self.assertRaises(a.construction.ConstructionRefusee):
            a.preuve_composants(r, preuve, candidat, '/nix/store/autre')

    def test_generation_differente_preservant_unites_hotes_et_postgres(self):
        candidat = json.loads((ROOT / 'operations/vision-multiutilisateur-candidat.json').read_text())
        paquet = json.loads((ROOT / 'operations/vision-identite-construction.json').read_text())['paquet']
        r = dict(version=1, keycloak_version='26.7.3', paquet=paquet,
            systeme_actif=candidat['audit']['systeme'], fournisseur_source=candidat['audit']['fournisseur'],
            systeme_amorcage='/nix/store/' + 'a' * 32 + '-systeme-amorcage',
            postgres_paquet='/nix/store/' + 'b' * 32 + '-postgresql', unite_identite='/nix/store/' + 'c' * 32 + '-unit',
            unite_cluster='/nix/store/' + 'd' * 32 + '-unit', unites_essentielles={},
            unites_conservees=True, hotes_conserves=True, postgres_production_conserve=True,
            parefeu_conserve=True, cluster_independant=True, postgres_tcp=False, inscriptions=False,
            mode_vision_oidc=False, preconditions_validees=False, activation=False, identite_humaine=False)
        for nom in ('sshd', 'postgresql', 'vision', 'matheval', 'mrj-auth'):
            r['unites_essentielles'][nom] = '/nix/store/' + 'e' * 32 + '-unit'
        a.verifier_resume(r, candidat, paquet)
        for cle in ('mode_vision_oidc', 'preconditions_validees', 'activation', 'inscriptions', 'postgres_tcp'):
            with self.subTest(cle=cle), self.assertRaises(a.construction.ConstructionRefusee):
                a.verifier_resume({**r, cle: True}, candidat, paquet)
        for cle in ('unites_conservees', 'hotes_conserves', 'postgres_production_conserve', 'cluster_independant'):
            with self.subTest(cle=cle), self.assertRaises(a.construction.ConstructionRefusee):
                a.verifier_resume({**r, cle: False}, candidat, paquet)
        with self.assertRaises(a.construction.ConstructionRefusee):
            a.verifier_resume({**r, 'systeme_amorcage': r['systeme_actif']}, candidat, paquet)
        faux = copy.deepcopy(r); del faux['unites_essentielles']['mrj-auth']
        with self.assertRaises(a.construction.ConstructionRefusee): a.verifier_resume(faux, candidat, paquet)


if __name__ == '__main__': unittest.main()
