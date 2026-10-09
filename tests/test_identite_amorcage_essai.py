"""Retour réel avec flock, données de fixture et API publique sans compte."""
import ast
import copy
import fcntl
import hashlib
import http.server
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def charger(nom, fichier):
    s=importlib.util.spec_from_file_location(nom, ROOT/'scripts'/fichier)
    m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


essai=charger('essai_test', 'vision-identite-amorcage-activer.py')
https=charger('https_test', 'identite-amorcage-https.py')


class Retour(unittest.TestCase):
    def test_diagnostic_interdit_pendant_essai_ou_apres_enregistrement(self):
        for marqueurs in ({'enregistre'}, {'commence'}):
            e=object.__new__(essai.Essai);e.marque=lambda n:n in marqueurs
            with self.subTest(marqueurs=marqueurs), patch.object(essai.construction,'verifier_socle') as socle:
                with self.assertRaises(RuntimeError):e.diagnostiquer()
                socle.assert_not_called()

    def test_copie_froide_corrompue_bloque_le_demarrage(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);p=d/'cluster-avant.tar.age';p.write_bytes(b'age-encryption.org/v1\nfixture privee');p.chmod(0o600)
            fd=os.open(d,os.O_RDONLY|os.O_DIRECTORY)
            try:
                e=object.__new__(essai.Essai);e.fd=fd
                preuve=dict(chiffree=True,cluster_arrete_avant_apres=True,restauration_reelle=False,
                    taille=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
                e.lire=lambda nom:preuve
                e.verifier_copie_froide()
                p.write_bytes(b'age-encryption.org/v1\nfixture autre!')
                with self.assertRaises(RuntimeError):e.verifier_copie_froide()
                p.chmod(0o644)
                with self.assertRaises(ValueError):e.verifier_copie_froide()
            finally:os.close(fd)

    def test_attribut_ne_masque_aucune_action_du_controleur(self):
        source=ast.parse((ROOT/'scripts/vision-identite-amorcage-activer.py').read_text())
        classe=next(n for n in source.body if isinstance(n,ast.ClassDef) and n.name=='Essai')
        methodes={n for n,v in vars(essai.Essai).items() if callable(v)}
        attributs={n.attr for n in ast.walk(classe) if isinstance(n,ast.Attribute) and
            isinstance(n.ctx,ast.Store) and isinstance(n.value,ast.Name) and n.value.id=='self'}
        self.assertEqual(methodes&attributs,set(),'Une chaîne d’unité ne doit pas masquer une action exécutable')

    def fixture(self, root):
        d=root/'etat'; d.mkdir(); outils=root/'outils'; outils.mkdir()
        log=root/'operations.txt'; courant=root/'courant'; profil=root/'profil'
        ancien=root/'ancienne'; (ancien/'bin').mkdir(parents=True)
        nouveau=root/'nouvelle'; nouveau.mkdir()
        courant.symlink_to(nouveau); profil.symlink_to(nouveau)
        configuration=root/'configuration.nix'; configuration.write_text('nouvelle')
        (d/'configuration-avant.nix').write_text('ancienne')
        (d/'finalisation.lock').touch(mode=0o600)
        for nom in ('bash','flock','cp','mv','touch','readlink','python3','rm','ln'):
            (outils/nom).symlink_to(shutil.which(nom))
        for nom, texte in {
            'systemctl': '#!/bin/sh\nprintf "%s\\n" "$*" >> '+str(log)+'\n',
            'nix-env': '#!/usr/bin/env python3\nimport pathlib,sys\np=pathlib.Path(sys.argv[2]); p.unlink(); p.symlink_to(sys.argv[4])\n',
        }.items():
            (outils/nom).write_text(texte); (outils/nom).chmod(0o700)
        script=ancien/'bin/switch-to-configuration'
        script.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> '+str(log)+'\nif [ "$1" = test ]; then rm '+str(courant)+'; ln -s '+str(ancien)+' '+str(courant)+'; fi\n'); script.chmod(0o700)
        retour=d/'retour.sh'
        retour.write_text(essai.script_retour(d,str(ancien),str(ancien),outils,
            configuration=str(configuration),profil=str(profil),courant=str(courant),worker='fixture.service'))
        retour.chmod(0o700)
        return d,retour,configuration,profil,courant,ancien,nouveau,log

    def test_retour_retablit_entree_et_profils_sans_sql(self):
        with tempfile.TemporaryDirectory() as tmp:
            d,retour,config,profil,courant,ancien,_,log=self.fixture(Path(tmp))
            subprocess.run(['bash','-n',retour],check=True)
            subprocess.run([retour],check=True,capture_output=True)
            self.assertEqual(config.read_text(),'ancienne')
            self.assertEqual(profil.resolve(),ancien); self.assertEqual(courant.resolve(),ancien)
            self.assertTrue((d/'retour-termine').exists())
            lignes=log.read_text().splitlines(); self.assertEqual(lignes[:3],['stop fixture.service','boot','test'])
            self.assertNotIn('psql',log.read_text())

    def test_verrou_et_marqueur_empechent_retour_apres_enregistrement(self):
        with tempfile.TemporaryDirectory() as tmp:
            d,retour,config,profil,courant,_,nouveau,log=self.fixture(Path(tmp))
            with (d/'finalisation.lock').open('r+') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX)
                p=subprocess.Popen([retour],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                try:
                    time.sleep(.1); self.assertIsNone(p.poll())
                    (d/'enregistre').touch()
                finally: fcntl.flock(lock,fcntl.LOCK_UN)
                out,err=p.communicate(timeout=5); self.assertEqual(p.returncode,0,err.decode())
            self.assertFalse((d/'retour-commence').exists()); self.assertFalse(log.exists())
            self.assertEqual(config.read_text(),'nouvelle'); self.assertEqual(profil.resolve(),nouveau)

    def test_un_second_declenchement_ne_defait_pas_une_operation_suivante(self):
        with tempfile.TemporaryDirectory() as tmp:
            d,retour,config,profil,courant,ancien,nouveau,log=self.fixture(Path(tmp))
            subprocess.run([retour],check=True,capture_output=True)
            config.write_text('operation suivante'); profil.unlink(); profil.symlink_to(nouveau)
            courant.unlink(); courant.symlink_to(nouveau); avant=log.read_bytes()
            subprocess.run([retour],check=True,capture_output=True)
            self.assertEqual(log.read_bytes(),avant); self.assertEqual(config.read_text(),'operation suivante')
            self.assertEqual(courant.resolve(),nouveau); self.assertEqual(profil.resolve(),nouveau)

    def test_finalisation_refuse_un_retour_deja_commence(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp); (d/'finalisation.lock').touch(mode=0o600)
            for n in ('teste','retour-commence'): (d/n).touch(mode=0o600)
            objet=essai.Essai.__new__(essai.Essai); objet.fd=os.open(d,os.O_RDONLY|os.O_DIRECTORY)
            objet.d=d; appels=[]; objet.commande=lambda *a,**k: appels.append(a)
            try:
                with self.assertRaisesRegex(RuntimeError,'Enregistrement interdit'): objet.finaliser()
                self.assertEqual(appels,[])
            finally: os.close(objet.fd)

    def test_dry_refuse_reseau_postgres_et_actions_inattendues(self):
        prefixe='would activate the configuration...\n'
        self.assertEqual(essai.verifier_dry(prefixe+'would reload the following units: nginx.service\n'),1)
        for texte in ('would restart systemd','would stop swap device: /dev/fixture',
                'would restart the following units: postgresql.service',
                'would stop the following units: nginx.service, sshd.service',
                'would reload the following units: vision.service'):
            with self.assertRaises(RuntimeError): essai.verifier_dry(prefixe+texte)
        with self.assertRaises(RuntimeError): essai.verifier_dry('inconnu')

    def test_credential_ne_tourne_pas_et_exige_fin_de_ligne_et_droits(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp); fd=os.open(d,os.O_RDONLY|os.O_DIRECTORY)
            try:
                essai.secret_amorcage(fd); p=d/'amorcage-admin.secret'; original=p.read_bytes()
                self.assertEqual(len(original),44); self.assertTrue(original.endswith(b'\n'))
                essai.secret_amorcage(fd); self.assertEqual(p.read_bytes(),original)
                p.write_bytes(original[:-1])
                with self.assertRaises(RuntimeError): essai.secret_amorcage(fd)
                p.write_bytes(original); p.chmod(0o644)
                with self.assertRaises(ValueError): essai.secret_amorcage(fd)
            finally: os.close(fd)

    def test_preuve_ne_permet_pas_mode_commun_ou_autre_generation(self):
        preuve=json.loads((ROOT/'operations/vision-identite-amorcage-qualification.json').read_text())
        candidat=json.loads((ROOT/'operations/vision-multiutilisateur-candidat.json').read_text())
        ancienne=copy.deepcopy(preuve);ancienne.pop('configuration_nginx_native',None)
        with self.assertRaises(RuntimeError):essai.preuve_valide(ancienne,ancienne,candidat)
        preuve={**preuve,'configuration_nginx_native':True}
        essai.preuve_valide(preuve,preuve,candidat)
        for cle,valeur in [('configuration_nginx_native',False),('activation',True),('identite_humaine',True),('proprietaires',2),('mode_vision_oidc',True),('systeme_actif','/nix/store/'+'a'*32+'-autre')]:
            change={**preuve,cle:valeur}
            with self.assertRaises(RuntimeError): essai.preuve_valide(change,change,candidat)
        with self.assertRaises(RuntimeError): essai.entree_nix('/tmp/${injection}.nix','/tmp/module.nix',None)


class Public(unittest.TestCase):
    def test_issuer_refus_et_redirect_sont_verifies_sur_http_de_fixture(self):
        mode={'erreur':None}; visites=[]
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self,*a): pass
            def do_GET(self):
                visites.append(self.path); origine='http://127.0.0.1:'+str(self.server.server_port)
                code=404; body=b'{}'
                if self.path=='/realms/mrjam/.well-known/openid-configuration':
                    code=200
                    issuer=(origine if mode['erreur']!='issuer' else 'https://exemple.invalid')+'/realms/mrjam'
                    body=json.dumps(dict(issuer=issuer,authorization_endpoint=issuer+'/auth',token_endpoint=issuer+'/token',jwks_uri=issuer+'/certs')).encode()
                    if mode['erreur']=='redirect': code=302
                elif self.path.endswith('/certs'):
                    code=200; body=json.dumps({'keys':[{'kid':'fixture','kty':'RSA','n':'public','e':'AQAB',**({'d':'prive'} if mode['erreur']=='cle' else {})}]}).encode()
                elif self.path.endswith('.tar.gz'): code=200; body=b'\x1f\x8bfixture'
                elif self.path=='/admin/' and mode['erreur']=='admin': code=200
                self.send_response(code); self.send_header('Referrer-Policy','no-referrer')
                self.send_header('Strict-Transport-Security','max-age=31536000')
                if code==302: self.send_header('Location','https://exemple.invalid/vol')
                self.end_headers(); self.wfile.write(body)
            do_POST=do_GET
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
        t=threading.Thread(target=server.serve_forever,daemon=True); t.start()
        try:
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),https.SansRedirection())
            origine='http://127.0.0.1:'+str(server.server_port)
            resultat=https.verifier(opener,origine); self.assertFalse(resultat['compte_utilise'])
            for erreur in ('issuer','redirect','cle','admin'):
                mode['erreur']=erreur
                with self.assertRaises(ValueError): https.verifier(opener,origine)
            self.assertNotIn('/vol',visites)
        finally: server.shutdown(); server.server_close(); t.join()


if __name__=='__main__': unittest.main()
