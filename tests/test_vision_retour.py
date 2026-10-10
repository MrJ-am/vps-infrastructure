"""Exécuter le vrai shell de retour avec pannes et interruption de processus.

Seuls systemd/Nix/PostgreSQL sont simulés ; fichiers, liens, verrous, sync,
conditions, marqueurs et reprises utilisent réellement l'opérateur généré.
Les transactions SQL sont aussi qualifiées nativement en CI PostgreSQL17.
"""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('qualification_retour',ROOT/'scripts/vision-essai-qualification.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

FAUX=r'''#!/usr/bin/env python3
import json,os,signal,sys
from pathlib import Path
n=Path(sys.argv[0]).name;a=sys.argv[1:]
p=Path(os.environ['VISION_FIXTURE']);s=json.loads(p.read_text())
def sauver():p.write_text(json.dumps(s))
def interruption(point):
 if s.get('interruption')==point:
  s.pop('interruption');sauver();os.kill(os.getppid(),signal.SIGKILL)
def refuse(point):
 if s.get('refus')==point:sys.exit(7)
if n=='runuser':os.execv(a[3],a[3:])
if n=='pg_dump':
 s['dumps']+=1;sauver();sys.stdout.write(json.dumps(s['nouveau']));sys.stdout.flush()
 interruption('copie');sys.exit(0)
if n=='pg_restore':
 if '--list' in a:json.loads(Path(a[-1]).read_text());sys.exit(0)
 refuse('restauration');s['ancien']=json.load(sys.stdin);s['restaurations']+=1;sauver()
 interruption('restauration');sys.exit(0)
if n=='psql':
 contenu=sys.stdin.read()
 if '-d' in a and a[a.index('-d')+1]=='vision':
  refuse('acl');s['acl']+=1;sauver();interruption('acl');sys.exit(0)
 valeur=s['nouveau'] if a[a.index('-h')+1]=='nouveau' else s['ancien']
 print(json.dumps(valeur,sort_keys=True));sys.exit(0)
if n=='nix-env':
 cible=a[a.index('--set')+1];profil=Path(a[a.index('--profile')+1]);profil.unlink(missing_ok=True);profil.symlink_to(cible)
 sys.exit(0)
if n=='switch-to-configuration':
 refuse('generation')
 if a==['test']:
  p2=Path(s['courant']);p2.unlink(missing_ok=True);p2.symlink_to(s['generation'])
 sys.exit(0)
if n=='systemctl':
 s['appels'].append(a);sauver()
 if a[0]=='show':
  if '--property=LoadState' in a:print('loaded')
  else:print(s['services'].get(a[1],'inactive'))
 elif a[0]=='stop':
  for u in a[1:]:s['services'][u]='inactive'
  sauver()
 elif a[0]=='start':
  for u in a[1:]:
   ferme=any((Path(s['unites'])/(u+'.d')).glob('90-vision-retour-*.conf'))
   s['services'][u]='inactive' if ferme else 'active'
  sauver()
 elif a[0]=='is-active':sys.exit(0 if all(s['services'].get(u if u.endswith('.service') else u+'.service',s['services'].get(u))=='active' for u in a[1:]) else 3)
 sys.exit(0)
sys.exit(2)
'''


@unittest.skipUnless(os.geteuid()==0,'Recette root : qualification exécutée en root par check.yml')
class Retour(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.r=Path(self.tmp.name)
        self.d=self.r/('a'*40);self.d.mkdir(mode=0o700)
        self.outils=self.r/'outils';self.outils.mkdir()
        for n in ('bash','python3','flock','stat','mktemp','sync','mv','mkdir','rm','cp','dirname','cmp','readlink','ln'):
            (self.outils/n).symlink_to(shutil.which(n))
        self.faux=self.r/'faux';self.faux.write_text(FAUX);self.faux.chmod(0o700)
        self.pg=self.r/'postgres/bin';self.pg.mkdir(parents=True)
        for n in ('pg_dump','pg_restore','psql'):(self.pg/n).symlink_to(self.faux)
        for n in ('runuser','systemctl','nix-env'):(self.outils/n).symlink_to(self.faux)
        self.ancien=self.r/'generation';(self.ancien/'bin').mkdir(parents=True)
        (self.ancien/'bin/switch-to-configuration').symlink_to(self.faux)
        for n in ('profil','courant'):(self.r/n).symlink_to(self.r/'candidat')
        for n in ('configuration-avant.nix','identite-empreintes.sql','retour-acl.sql'):
            p=self.d/n;p.write_text('entrée synthétique\n');p.chmod(0o600)
        self.release=self.r/'release';self.release.mkdir();(self.release/'vision').write_text('backend synthétique')
        (self.d/'backend-avant').symlink_to(self.release)
        for n in ('identite-migree','sql-engage'):(self.d/n).write_text('1\n')
        self.unites=self.r/'unites';self.unites.mkdir()
        self.etat=self.r/'etat.json'
        self.etat.write_text(json.dumps(dict(nouveau=dict(sujet='stable',pwd='courant',otp='courant'),
            ancien=dict(sujet='stable',pwd='ancien',otp='ancien'),dumps=0,restaurations=0,acl=0,appels=[],
            unites=str(self.unites),courant=str(self.r/'courant'),generation=str(self.ancien),
            services={n:'active' for n in ('sshd','nginx','postgresql','vision','matheval','mrj-auth',
                'mrjam-amorcage-identite','nginx.service','vision.service','mrj-auth.service','keycloak.service')})))
        self.shell=self.r/'retour.sh';self.shell.write_text(m.script_retour(self.d,str(self.ancien),self.outils,
            self.pg.parent,self.outils/'runuser','worker.service',configuration=str(self.r/'configuration.nix'),
            profil=str(self.r/'profil'),courant=str(self.r/'courant'),backend=str(self.r/'current'),
            verrou_deploiement=str(self.r/'deploy.lock'),unites=str(self.unites),socket_nouveau='nouveau',socket_ancien='ancien'))
        self.env={**os.environ,'VISION_FIXTURE':str(self.etat)}

    def tearDown(self):self.tmp.cleanup()
    def lire(self):return json.loads(self.etat.read_text())
    def changer(self,**valeurs):
        s=self.lire();s.update(valeurs);self.etat.write_text(json.dumps(s))
    def executer(self):return subprocess.run(['bash',str(self.shell)],env=self.env,capture_output=True,timeout=20)

    def test_courant_rejeu_sans_restaurer_un_dump_vision(self):
        r=self.executer();self.assertEqual(r.returncode,0,r.stdout.decode())
        s=self.lire();self.assertEqual(s['nouveau'],s['ancien']);self.assertEqual(s['restaurations'],1)
        self.assertFalse((self.d/'identite-courante-retour.dump').exists())
        self.assertTrue((self.d/'retour-termine').exists())
        self.assertEqual(self.executer().returncode,0);self.assertEqual(self.lire(),s)

    def test_interruptions_reprise_identite_courante_et_marques_durables(self):
        for point in ('copie','restauration','acl'):
            with self.subTest(point=point):
                # Un environnement indépendant pour chaque interruption réelle SIGKILL.
                self.tearDown();self.setUp();self.changer(interruption=point)
                self.assertNotEqual(self.executer().returncode,0)
                self.assertFalse((self.d/'retour-termine').exists())
                self.assertEqual(self.executer().returncode,0)
                s=self.lire();self.assertEqual(s['ancien'],s['nouveau'])
                self.assertEqual(s['dumps'],2 if point=='copie' else 1)

    def test_refus_acl_ferme_vision_et_rouvre_autres_sites(self):
        self.changer(refus='acl');r=self.executer();self.assertNotEqual(r.returncode,0)
        s=self.lire();self.assertEqual(s['services']['nginx.service'],'active')
        for u in ('vision.service','mrj-auth.service','keycloak.service','mrjam-amorcage-identite.service'):
            self.assertEqual(s['services'][u],'inactive')
            self.assertTrue(list((self.unites/(u+'.d')).glob('90-vision-retour-*.conf')))
        self.assertTrue((self.d/'identite-courante-retour.dump').exists())
        self.assertFalse((self.d/'retour-termine').exists())
        # Le transfert inverse est déjà durable : ne pas écraser une mise à jour
        # de l'ancien cluster à la reprise, même après un refus SQL ultérieur.
        s.pop('refus');s['ancien']['pwd']='apres-inversion';self.etat.write_text(json.dumps(s))
        self.assertEqual(self.executer().returncode,0)
        self.assertEqual(self.lire()['ancien']['pwd'],'apres-inversion')
        self.assertEqual(self.lire()['restaurations'],1)

    def test_refus_restauration_ne_rouvre_pas_identite_ou_vision(self):
        self.changer(refus='restauration');self.assertNotEqual(self.executer().returncode,0)
        s=self.lire();self.assertEqual(s['ancien']['pwd'],'ancien')
        self.assertFalse((self.d/'identite-retablie').exists())
        self.assertEqual(s['services']['vision.service'],'inactive')
        self.assertEqual(s['services']['nginx.service'],'active')

    def test_enregistrement_neutralise_et_retour_avant_sql(self):
        (self.d/'enregistre').write_text('1\n');s=self.lire()
        self.assertEqual(self.executer().returncode,0);self.assertEqual(self.lire(),s)
        (self.d/'enregistre').unlink()
        for n in ('identite-migree','sql-engage'):(self.d/n).unlink()
        self.assertEqual(self.executer().returncode,0)
        self.assertEqual(self.lire()['dumps'],0);self.assertEqual(self.lire()['acl'],0)


if __name__=='__main__':unittest.main()
