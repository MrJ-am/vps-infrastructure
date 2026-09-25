#!/usr/bin/env python3
"""Migration métier et publication Vision 2, depuis Actions, sous retour autonome.
Aucune restauration automatique en production : les nouvelles écritures restent
conservées. L'ancien modèle devient volontairement lisible mais non modifiable.
"""
import fcntl, hashlib, importlib.util, json, os, re, shlex, shutil, subprocess, sys, tarfile, time, uuid, zipfile
from pathlib import Path

def exiger(condition,message):
 if not condition:raise RuntimeError(message)
def executer(*args,entree=None):
 r=subprocess.run([str(a) for a in args],input=entree,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 if r.returncode:
  journal=os.environ.get('VISION_REFONTE_ERREURS')
  if journal:Path(journal).write_bytes(r.stderr)
  raise RuntimeError('Commande refusée : '+Path(str(args[0])).name+' ; détails privés conservés sur le VPS.')
 return r.stdout
def sauver(p,v):
 t=p.with_suffix('.nouveau');t.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n');os.replace(t,p)
def empreinte(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dossier(revision):
 exiger(re.fullmatch('[0-9a-f]{40}',revision),'Révision exacte requise')
 return Path('/root/vision-refonte-operations')/revision
def etat():
 return {'systeme':str(Path('/run/current-system').resolve()),'demarrage':str(Path('/nix/var/nix/profiles/system').resolve()),
  'configuration':empreinte(Path('/etc/nixos/configuration.nix')),
  **{n:str(Path('/srv/'+n+'/current').resolve()) for n in ('vision','vision-interface','matheval','logique')}}
def services():executer('systemctl','is-active','nginx','mrj-auth','vision','postgresql','matheval','sshd','postgresqlBackup-vision.timer','postgresqlBackup-matheval.timer')
def psql(base,sql,compte='postgres'):
 return executer('runuser','-u',compte,'--','psql','-XAtq','-v','ON_ERROR_STOP=1','-h','/run/postgresql','-d',base,'--file=-',entree=(("SET ROLE vision; SET client_min_messages=error; ")+sql).encode())
def proprietaire():
 # Les condensats ne quittent pas ce processus ; le rapport ne publie pas le nom.
 noms=[l.split(':',1)[0] for l in Path('/var/lib/vision/auth/htpasswd').read_text().splitlines() if l.strip() and not l.startswith('#')]
 exiger(len(noms)==1 and re.fullmatch('[A-Za-z0-9_.-]{1,64}',noms[0]),'Propriétaire historique non univoque : attribution nécessaire avant migration')
 return noms[0]
def importer_module(source):
 spec=importlib.util.spec_from_file_location('migration_vision',source/'scripts/refonte.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def wrapper(d,base,compte):
 p=d/('psql-'+base)
 p.write_text('#!/bin/sh\nexec '+shlex.quote(shutil.which('runuser'))+' -u '+shlex.quote(compte)+' -- '+shlex.quote(shutil.which('psql'))+' -h /run/postgresql -d '+shlex.quote(base)+' -c '+shlex.quote('SET ROLE vision; SET client_min_messages=error')+' "$@"\n');p.chmod(0o700)
 return p
def migrations(source,base,compte):
 for p in sorted((source/'migrations').glob('*.sql')):psql(base,p.read_text(),compte)
def empreinte_donnees(base):
 # Empreintes locales uniquement, jamais le contenu ni les identifiants en sortie.
 tables=('vision_fiches','vision_items','vision_liens','vision_episodes',
         'vision_contextes','vision_journal','vision_migrations_metier',
         'vision_memory_sheets','vision_memory_observations')
 return {table:psql(base,"SELECT md5(coalesce((SELECT jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text)::text FROM "+table+" t),'[]'))").decode().strip()
         for table in tables}

def migration_sequentielle(source,base):
 fichier=source/'migrations/010_consigne_revision.sql'
 exiger(fichier.is_file(),'Migration de révision absente')
 avant=empreinte_donnees(base)
 psql(base,fichier.read_text())
 exiger(empreinte_donnees(base)==avant,'Une donnée a changé pendant la migration de révision')
 exiger(psql(base,'SELECT count(*) FROM vision_schema_migrations WHERE version=10').strip()==b'1','Migration 010 non enregistrée')
 u=proprietaire()
 # Le propriétaire est validé comme identifiant ASCII sans apostrophe.
 requete="SELECT jsonb_array_length(vision_preparer('"+u+"',jsonb_build_object('fiche_id',id,'limite',8,'repeter',true))->'usage_assistant'->'items') FROM vision_fiches WHERE utilisateur='"+u+"' AND archive_a IS NULL ORDER BY id LIMIT 1"
 nombre=psql(base,requete).decode().strip()
 exiger(nombre in ('0','1'),'La préparation révèle plusieurs items')
 return {'mise_a_jour':True,'donnees_preservees':True,'migration_010':True,'selection_maximale':1}

def sauvegarder(d,nom):
 p=d/(nom+'.dump')
 with p.open('wb') as f:
  r=subprocess.run(['runuser','-u','postgres','--','pg_dump','-Fc','-h','/run/postgresql','-d','vision'],stdout=f,stderr=subprocess.PIPE)
 exiger(r.returncode==0 and p.stat().st_size>0,'Sauvegarde absente ou refusée')
 return p

def restauration_et_plan(d,source,sauvegarde,nom):
 base='vision_refonte_'+uuid.uuid4().hex[:16]
 executer('runuser','-u','postgres','--','createdb','-h','/run/postgresql','-O','vision',base)
 try:
  # stdin permet au compte postgres de restaurer sans ouvrir le dossier root.
  with sauvegarde.open('rb') as f:
   r=subprocess.run(['runuser','-u','postgres','--','pg_restore','--exit-on-error','--no-owner','--role=vision','-h','/run/postgresql','-d',base],stdin=f,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
  exiger(r.returncode==0,'Restauration isolée refusée')
  # Une collection v2 existante exige une migration additive, sans nouvel import.
  existante=bool(int(psql(base,"SELECT count(*) FROM vision_migrations_metier WHERE cle='fiches-items-v2'").strip()))
  if existante:
   rapport=migration_sequentielle(source,base)
   sauver(d/(nom+'-rapport.json'),rapport)
   return None,rapport
  migrations(source,base,'postgres')
  os.environ['VISION_PSQL']=str(wrapper(d,base,'postgres'));m=importer_module(source);plan=m.preparer();u=proprietaire()
  (d/(nom+'-plan-prive.json')).write_text(json.dumps(plan,ensure_ascii=False,indent=2))
  avant=json.loads(psql(base,"SELECT jsonb_build_object('fiches',(SELECT count(*) FROM vision_fiches),'items',(SELECT count(*) FROM vision_items))"))
  exiger(avant=={'fiches':0,'items':0},'Collection sans migration initiale connue : opération refusée')
  simule=m.appliquer(u,plan,True)
  exiger(json.loads(psql(base,'SELECT count(*) FROM vision_items'))==0,'La simulation a laissé des données')
  applique=m.appliquer(u,plan);rejeu=m.appliquer(u,plan)
  exiger(rejeu.get('rejeu') and applique['items_apres']==plan['rapport']['items_prevus'],'Relance de migration non idempotente')
  # Mesures et sources privées restent locales. Seuls les agrégats sont publiables.
  rapport={**applique,'restauration_verifiee':True,'simulation_annulee':True,'rejeu_verifie':True,
   'sauvegarde_sha256':empreinte(sauvegarde),'sauvegarde_octets':sauvegarde.stat().st_size}
  sauver(d/(nom+'-rapport.json'),rapport)
  return plan,rapport
 finally:
  executer('runuser','-u','postgres','--','dropdb','-h','/run/postgresql',base)

def decompresser(source,archive):
 with tarfile.open(archive,'r:gz') as t:
  for f in t.getmembers():exiger(not f.issym() and not f.islnk() and (source/f.name).resolve().is_relative_to(source.resolve()),'Archive source non sûre')
  t.extractall(source,filter='data')
def interface(d,archive,revision):
 cible=Path('/srv/vision-interface/releases')/revision
 exiger(not cible.exists(),'Publication statique déjà existante')
 cible.mkdir(mode=0o755,parents=True)
 with zipfile.ZipFile(archive) as z:
  for n in z.namelist():exiger((cible/n).resolve().is_relative_to(cible),'Archive interface non sûre')
  z.extractall(cible)
 m=json.loads((cible/'manifest.json').read_text());exiger(m['revisionApplication']==revision,'Révision du manifeste différente')
 for n,h in m['fichiers'].items():exiger(empreinte(cible/n)==h,'Empreinte interface différente')
 executer('chmod','-R','a+rX',cible)
 return str(cible)
def preparer(revision):
 d=dossier(revision);src=d/'source';demande=json.loads((src/'operations/vision-refonte-candidat.json').read_text());avant=etat();services()
 exiger(not (d/'preparation.json').exists(),'Opération déjà préparée')
 exiger(avant['systeme']==avant['demarrage'],'Générations désynchronisées')
 app=demande['application'];exiger(re.fullmatch('[0-9a-f]{40}',app),'Révision applicative invalide')
 for n,h in demande['fichiers'].items():exiger(empreinte(src/n)==h,'Archive différente du candidat validé')
 cible=Path('/srv/vision/releases')/app
 exiger(not cible.exists(),'Publication serveur déjà existante')
 cible.mkdir(mode=0o755,parents=True);decompresser(cible,src/'vendor/vision-refonte-source.tar.gz')
 exiger((cible/'revision-application.txt').read_text().strip()==app,'Source différente')
 executer('chown','-R','vision:vision',cible)
 nixpkgs=executer('nix-instantiate','--find-file','nixpkgs').decode().strip()
 executer('nix-shell','-I','nixpkgs='+nixpkgs,'-p','sbcl','--run','cd '+shlex.quote(str(cible))+' && sh build.sh')
 exiger((cible/'vision').stat().st_size>1000000,'Binaire absent')
 executer('chmod','-R','a+rX',cible)
 statique=interface(d,src/'vendor/vision-refonte-interface.zip',app)
 backup=sauvegarder(d,'preparation');plan,rapport=restauration_et_plan(d,cible,backup,'preparation')
 temoin=d/'timer-verifie'
 executer('systemd-run','--unit=vision-refonte-temoin-'+revision[:12],'--on-active=2s','--timer-property=AccuracySec=1s','/run/current-system/sw/bin/touch',temoin)
 for _ in range(15):
  if temoin.exists():break
  time.sleep(1)
 exiger(temoin.exists(),'Retour autonome non vérifié')
 exiger(etat()==avant,'État modifié pendant la préparation');services()
 sauver(d/'preparation.json',dict(revision=revision,application=app,avant=avant,serveur=str(cible),interface=statique,python=sys.executable,nixpkgs=nixpkgs,rapport=rapport))
 print(json.dumps(rapport,ensure_ascii=False));print('Sauvegarde restaurée, simulation et relance validées. Aucune écriture métier en production.')
def lire(revision):
 d=dossier(revision);return d,json.loads((d/'preparation.json').read_text())
def lien(cible,courant):
 p=Path(courant+'.refonte');p.unlink(missing_ok=True);p.symlink_to(cible);os.replace(p,courant)
def retour(revision):
 d,r=lire(revision)
 if (d/'enregistre').exists():return
 subprocess.run(['systemctl','stop','vision-refonte-appliquer-'+revision[:12]],check=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 with (d/'bascule.lock').open('a') as v:
  fcntl.flock(v,fcntl.LOCK_EX)
  if (d/'enregistre').exists():return
  exiger((d/'engage').exists(),'Aucune activation engagée')
  courant=etat();exiger(all(courant[k]==r['avant'][k] for k in ('systeme','demarrage','configuration','matheval','logique')),'État système modifié : retour refusé')
  exiger(courant['vision'] in (r['avant']['vision'],r['serveur']) and courant['vision-interface'] in (r['avant']['vision-interface'],r['interface']),'Publication concurrente : retour refusé')
  (d/'retour-engage').touch();executer('systemctl','stop','vision')
  lien(r['avant']['vision'],'/srv/vision/current');lien(r['avant']['vision-interface'],'/srv/vision-interface/current')
  executer('systemctl','start','vision');services();sauver(d/'retour.json',dict(etat=etat(),restauration_base=False,donnees_v2_conservees=True))
 executer('systemctl','stop','vision-refonte-retour-'+revision[:12]+'.timer')
def appliquer(revision):
 d,r=lire(revision)
 with (d/'bascule.lock').open('a') as v:
  fcntl.flock(v,fcntl.LOCK_EX);exiger(etat()==r['avant'] and not (d/'retour-engage').exists(),'État modifié depuis la préparation')
  executer('systemctl','stop','vision')
  # Nouveau dump après arrêt de toutes les écritures applicatives. Le plan de
  # préparation n'est jamais réutilisé sur des données qui ont pu évoluer.
  backup=sauvegarder(d,'activation');plan,rapport=restauration_et_plan(d,Path(r['serveur']),backup,'activation')
  if plan is None:
   resultat=migration_sequentielle(Path(r['serveur']),'vision')
   exiger(resultat['donnees_preservees'],'Mise à jour non confirmée')
  else:
   migrations(Path(r['serveur']),'vision','vision')
   os.environ['VISION_PSQL']=str(wrapper(d,'vision','vision'));m=importer_module(Path(r['serveur']))
   resultat=m.appliquer(proprietaire(),plan)
   exiger(resultat.get('enregistre') and resultat['items_apres']==rapport['items_apres'],'Import non confirmé')
  (d/'migration-commise').touch();lien(r['serveur'],'/srv/vision/current');lien(r['interface'],'/srv/vision-interface/current')
  executer('systemctl','start','vision');services();sauver(d/'essai.json',dict(etat=etat(),rapport=rapport))
 print('Migration atomique réalisée et deux publications activées sous retour autonome.')
def demarrer(revision):
 d,r=lire(revision)
 exiger(not any((d/n).exists() for n in ('engage','retour-engage','enregistre')),'Opération déjà engagée')
 exiger(etat()==r['avant'],'Nouvel audit nécessaire');(d/'engage').touch()
 script=d/'source/scripts/vision-refonte-deployer.py'
 executer('systemd-run','--unit=vision-refonte-retour-'+revision[:12],'--on-active=20m','--timer-property=AccuracySec=1s','--setenv=PATH='+os.environ['PATH'],r['python'],script,'retour',revision)
 executer('systemctl','is-active','vision-refonte-retour-'+revision[:12]+'.timer')
 executer('systemd-run','--wait','--pipe','--unit=vision-refonte-appliquer-'+revision[:12],'--setenv=PATH='+os.environ['PATH'],r['python'],script,'appliquer',revision)
def finaliser(revision):
 d,r=lire(revision)
 with (d/'bascule.lock').open('a') as v:
  fcntl.flock(v,fcntl.LOCK_EX);exiger((d/'essai.json').exists() and not (d/'retour-engage').exists(),'Essai absent ou retour engagé')
  attendu={**r['avant'],'vision':r['serveur'],'vision-interface':r['interface']};exiger(etat()==attendu,'État différent du candidat');services()
  sauver(d/'termine.json',dict(revision=revision,application=r['application'],etat=etat(),rapport=json.loads((d/'activation-rapport.json').read_text())));(d/'enregistre').touch()
 executer('systemctl','stop','vision-refonte-retour-'+revision[:12]+'.timer')
 print('Publication enregistrée ; retour désarmé, anciennes versions et données conservées.')
if __name__=='__main__':
 exiger(os.geteuid()==0,'Exécution réservée au runner administratif');os.umask(0o077)
 os.environ['VISION_REFONTE_ERREURS']=str(dossier(sys.argv[2])/'commande-echec-prive.log')
 {'preparer':preparer,'demarrer':demarrer,'appliquer':appliquer,'finaliser':finaliser,'retour':retour}[sys.argv[1]](sys.argv[2])
