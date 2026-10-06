#!/usr/bin/env python3
"""Publication additive Vision 2.6 depuis Actions, sous retour autonome.
Aucune restauration automatique en production : les nouvelles écritures restent
conservées. Le retour restaure les fonctions compatibles, jamais les données métier.
"""
import fcntl, hashlib, importlib.util, json, os, re, shlex, shutil, subprocess, sys, tarfile, time, uuid, zipfile
from pathlib import Path

def exiger(condition,message):
 if not condition:raise RuntimeError(message)
def executer(*args,entree=None):
 r=subprocess.run([str(a) for a in args],input=entree,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 if r.returncode:
  journal=os.environ.get('VISION_AUTONOMIE_ERREURS')
  if journal:Path(journal).write_bytes(r.stderr)
  raise RuntimeError('Commande refusée : '+Path(str(args[0])).name+' ; détails privés conservés sur le VPS.')
 return r.stdout
def sauver(p,v):
 t=p.with_suffix('.nouveau');t.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n');os.replace(t,p)
def empreinte(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dossier(revision):
 exiger(re.fullmatch('[0-9a-f]{40}',revision),'Révision exacte requise')
 return Path('/root/vision-autonomie-operations')/revision
def etat():
 return {'systeme':str(Path('/run/current-system').resolve()),'demarrage':str(Path('/nix/var/nix/profiles/system').resolve()),
  'configuration':empreinte(Path('/etc/nixos/configuration.nix')),
  **{n:str(Path('/srv/'+n+'/current').resolve()) for n in ('vision','vision-interface','matheval','logique')}}
def services():executer('systemctl','is-active','nginx','mrj-auth','vision','postgresql','matheval','sshd','postgresqlBackup-vision.timer','postgresqlBackup-matheval.timer','vision-embeddings','nextcloud-backup.timer')
def psql(base,sql,compte='postgres'):
 return executer('runuser','-u',compte,'--','psql','-XAtq','-v','ON_ERROR_STOP=1','-h','/run/postgresql','-d',base,'--file=-',entree=(("SET ROLE vision; SET client_min_messages=error; ")+sql).encode())
def empreinte_donnees(base):
 # Toutes les données applicatives, y compris le contenu, les dates et les rapports.
 tables=psql(base,"SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename LIKE 'vision_%' AND tablename<>'vision_schema_migrations' ORDER BY tablename").decode().splitlines()
 exiger(all(re.fullmatch('vision_[a-z_]+',n) for n in tables),'Table inattendue')
 return {table:psql(base,"SELECT md5(coalesce((SELECT jsonb_agg(to_jsonb(t)-ARRAY['duree_seance_courte_minutes','datation_reference','datation'] ORDER BY (to_jsonb(t)-ARRAY['duree_seance_courte_minutes','datation_reference','datation'])::text)::text FROM "+table+" t),'[]'))").decode().strip() for table in tables}

def fonctions(base):
 # Définitions exactes et privées : restaurer le contrat ancien sans rejouer une
 # migration historique ni effacer les données collectées pendant l'essai.
 return psql(base,"SELECT string_agg(pg_get_functiondef(p.oid)||';', E'\\n' ORDER BY p.oid) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proname IN ('vision_politique','vision_evaluer','vision_clore_seance_v2','vision_clore_seance','vision_commande','vision_revision_contrat')").decode()

def migration_sequentielle(source,base):
 exiger(psql(base,'SELECT count(*) FROM vision_schema_migrations WHERE version BETWEEN 1 AND 16').strip()==b'16','Socle 001–016 absent')
 avant=empreinte_donnees(base)
 for nom in ('017_tutorat_temps.sql','018_consultation.sql'):
  psql(base,(source/'migrations'/nom).read_text())
 exiger(empreinte_donnees(base)==avant,'Une donnée historique a changé')
 exiger(psql(base,'SELECT vision_revision_contrat(); SELECT vision_creation_contrat()').strip()==b'7\n1','Contrats incohérents')
 return dict(migrations=[17,18],contrat_sql=7,donnees_preservees=True,tables_preservees=len(avant),seances_de_test_production=0)

def sauvegarder(d,nom):
 p=d/(nom+'.dump')
 with p.open('wb') as f:
  r=subprocess.run(['runuser','-u','postgres','--','pg_dump','-Fc','-h','/run/postgresql','-d','vision'],stdout=f,stderr=subprocess.PIPE)
 exiger(r.returncode==0 and p.stat().st_size>0,'Sauvegarde absente ou refusée')
 return p

def restauration_et_plan(d,source,sauvegarde,nom):
 # Base jetable : aucun serveur de test ne reçoit l'adresse de la production.
 base='vision_autonomie_'+uuid.uuid4().hex[:16]
 executer('runuser','-u','postgres','--','createdb','-h','/run/postgresql','-O','vision',base)
 try:
  # pgvector nécessite le superutilisateur ; les extensions sont préparées avant
  # pg_restore, puis leurs instructions CREATE/COMMENT sont exclues du TOC.
  executer('runuser','-u','postgres','--','psql','-XAtq','-v','ON_ERROR_STOP=1','-d',base,'-c','CREATE EXTENSION vector; CREATE EXTENSION pg_trgm;')
  toc=executer('pg_restore','--list',sauvegarde).decode()
  liste=d/(nom+'-toc-prive.txt')
  liste.write_text('\n'.join(l for l in toc.splitlines() if not re.search(r' (?:EXTENSION|COMMENT - EXTENSION) ',l))+'\n')
  # Le compte postgres lit le TOC par stdin ; le dump est copié vers un chemin
  # privé qui lui appartient et est supprimé dans finally.
  temporaire=Path('/var/lib/postgresql')/(base+'.dump')
  shutil.copyfile(sauvegarde,temporaire);executer('chown','postgres:postgres',temporaire);temporaire.chmod(0o600)
  try:
   executer('runuser','-u','postgres','--','pg_restore','--exit-on-error','--no-owner','--role=vision','-h','/run/postgresql','-d',base,'--use-list=/dev/stdin',temporaire,entree=liste.read_bytes())
  finally:temporaire.unlink(missing_ok=True)
  definitions=fonctions(base)
  rapport=migration_sequentielle(source,base)
  avant=empreinte_donnees(base)
  psql(base,(source/'tests/coherence_cloture.sql').read_text())
  exiger(empreinte_donnees(base)==avant,'Le contrôle annulé a laissé des données')
  # Essayer le vrai retour SQL, puis la réinstallation additive ; les nouvelles
  # colonnes restent présentes, sans restauration d'un dump en production.
  psql(base,'BEGIN;\n'+definitions+'\nCOMMIT;')
  exiger(psql(base,'SELECT vision_revision_contrat()').strip()==b'6','Retour SQL incompatible')
  exiger(empreinte_donnees(base)==avant,'Le retour SQL a modifié les données')
  migration_sequentielle(source,base)
  rapport.update(restauration_verifiee=True,retour_sql_verifie=True,tests_annules=True,
    sauvegarde_sha256=empreinte(sauvegarde),sauvegarde_octets=sauvegarde.stat().st_size)
  sauver(d/(nom+'-rapport.json'),rapport)
  return None,rapport
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
 d=dossier(revision);src=d/'source';demande=json.loads((src/'operations/vision-autonomie-candidat.json').read_text());avant=etat();services()
 exiger(not (d/'preparation.json').exists(),'Opération déjà préparée')
 exiger(avant['systeme']==avant['demarrage']=='/nix/store/y1azkcagkf54nq5vjn4j16g5v1c61c4c-nixos-system-nixos-26.05.8639.c5c4a43b0e80','Écart avec audit 37427041831')
 exiger(avant['vision'].endswith('/c0bfcac66b9ee52e282bb895ec6aed3921a86266') and avant['vision-interface'].endswith('/c0bfcac66b9ee52e282bb895ec6aed3921a86266'),'Publication différente de l’audit')
 app=demande['application'];exiger(re.fullmatch('[0-9a-f]{40}',app),'Révision applicative invalide')
 for n,h in demande['fichiers'].items():exiger(empreinte(src/n)==h,'Archive différente du candidat validé')
 cible=Path('/srv/vision/releases')/app
 exiger(not cible.exists(),'Publication serveur déjà existante')
 cible.mkdir(mode=0o755,parents=True);decompresser(cible,src/'vendor/vision-autonomie-source.tar.gz')
 exiger((cible/'revision-application.txt').read_text().strip()==app,'Source différente')
 # Sources immuables appartenant à root, lisibles par le service.
 nixpkgs=executer('nix-instantiate','--find-file','nixpkgs').decode().strip()
 executer('nix-shell','-I','nixpkgs='+nixpkgs,'-p','sbcl','--run','cd '+shlex.quote(str(cible))+' && sh build.sh')
 exiger((cible/'vision').stat().st_size>1000000,'Binaire absent')
 # L'adresse est dérivée du registre réel de routage. Le wrapper appartient à la
 # release et disparaît avec le retour applicatif ; aucun NixOS reconstruit.
 projet=json.loads((src/'projects.json').read_text())['vision']
 domaine=projet['domain'];prefixe=projet['prefix']
 exiger(re.fullmatch('[a-zA-Z0-9.-]+',domaine) and re.fullmatch('/[a-zA-Z0-9/_-]*|',prefixe),'Routage invalide')
 (cible/'vision').rename(cible/'vision-lisp')
 (cible/'vision').write_text('#!/bin/sh\nexport VISION_PUBLIC_MCP_URL='+shlex.quote('https://'+domaine+prefixe+'/mcp')+'\nexec '+shlex.quote(str(cible/'vision-lisp'))+' "$@"\n')
 (cible/'vision').chmod(0o755)
 executer('chmod','-R','a+rX',cible)
 statique=interface(d,src/'vendor/vision-autonomie-interface.zip',app)
 backup=sauvegarder(d,'preparation');plan,rapport=restauration_et_plan(d,cible,backup,'preparation')
 temoin=d/'timer-verifie'
 executer('systemd-run','--unit=vision-autonomie-temoin-'+revision[:12],'--on-active=2s','--timer-property=AccuracySec=1s','/run/current-system/sw/bin/touch',temoin)
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
 subprocess.run(['systemctl','stop','vision-autonomie-appliquer-'+revision[:12]],check=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 with (d/'bascule.lock').open('a') as v:
  fcntl.flock(v,fcntl.LOCK_EX)
  if (d/'enregistre').exists():return
  exiger((d/'engage').exists(),'Aucune activation engagée')
  courant=etat();exiger(all(courant[k]==r['avant'][k] for k in ('systeme','demarrage','configuration','matheval','logique')),'État système modifié : retour refusé')
  exiger(courant['vision'] in (r['avant']['vision'],r['serveur']) and courant['vision-interface'] in (r['avant']['vision-interface'],r['interface']),'Publication concurrente : retour refusé')
  (d/'retour-engage').touch();executer('systemctl','stop','vision')
  if (d/'fonctions-avant-prive.sql').exists():
   psql('vision','BEGIN;\n'+(d/'fonctions-avant-prive.sql').read_text()+'\nCOMMIT;')
  lien(r['avant']['vision'],'/srv/vision/current');lien(r['avant']['vision-interface'],'/srv/vision-interface/current')
  executer('systemctl','start','vision');services();sauver(d/'retour.json',dict(etat=etat(),restauration_base=False,donnees_v2_conservees=True))
 executer('systemctl','stop','vision-autonomie-retour-'+revision[:12]+'.timer')
def appliquer(revision):
 d,r=lire(revision)
 with (d/'bascule.lock').open('a') as v:
  fcntl.flock(v,fcntl.LOCK_EX);exiger(etat()==r['avant'] and not (d/'retour-engage').exists(),'État modifié depuis la préparation')
  executer('systemctl','stop','vision')
  # Nouveau dump après arrêt de toutes les écritures applicatives. Le plan de
  # préparation n'est jamais réutilisé sur des données qui ont pu évoluer.
  backup=sauvegarder(d,'activation');plan,rapport=restauration_et_plan(d,Path(r['serveur']),backup,'activation')
  (d/'fonctions-avant-prive.sql').write_text(fonctions('vision'))
  resultat=migration_sequentielle(Path(r['serveur']),'vision')
  exiger(resultat['donnees_preservees'],'Mise à jour non confirmée')
  (d/'migration-commise').touch();lien(r['serveur'],'/srv/vision/current');lien(r['interface'],'/srv/vision-interface/current')
  executer('systemctl','start','vision');services();sauver(d/'essai.json',dict(etat=etat(),rapport=rapport))
 print('Migration atomique réalisée et deux publications activées sous retour autonome.')
def demarrer(revision):
 d,r=lire(revision)
 exiger(not any((d/n).exists() for n in ('engage','retour-engage','enregistre')),'Opération déjà engagée')
 exiger(etat()==r['avant'],'Nouvel audit nécessaire');(d/'engage').touch()
 script=d/'source/scripts/vision-autonomie-deployer.py'
 executer('systemd-run','--unit=vision-autonomie-retour-'+revision[:12],'--on-active=30m','--timer-property=AccuracySec=1s','--setenv=PATH='+os.environ['PATH'],r['python'],script,'retour',revision)
 executer('systemctl','is-active','vision-autonomie-retour-'+revision[:12]+'.timer')
 executer('systemd-run','--wait','--pipe','--unit=vision-autonomie-appliquer-'+revision[:12],'--setenv=PATH='+os.environ['PATH'],r['python'],script,'appliquer',revision)
def finaliser(revision):
 d,r=lire(revision)
 with (d/'bascule.lock').open('a') as v:
  fcntl.flock(v,fcntl.LOCK_EX);exiger((d/'essai.json').exists() and not (d/'retour-engage').exists(),'Essai absent ou retour engagé')
  attendu={**r['avant'],'vision':r['serveur'],'vision-interface':r['interface']};exiger(etat()==attendu,'État différent du candidat');services()
  sauver(d/'termine.json',dict(revision=revision,application=r['application'],etat=etat(),rapport=json.loads((d/'activation-rapport.json').read_text())));(d/'enregistre').touch()
 executer('systemctl','stop','vision-autonomie-retour-'+revision[:12]+'.timer')
 print('Publication enregistrée ; retour désarmé, anciennes versions et données conservées.')
if __name__=='__main__':
 exiger(os.geteuid()==0,'Exécution réservée au runner administratif');os.umask(0o077)
 os.environ['VISION_AUTONOMIE_ERREURS']=str(dossier(sys.argv[2])/'commande-echec-prive.log')
 {'preparer':preparer,'demarrer':demarrer,'appliquer':appliquer,'finaliser':finaliser,'retour':retour}[sys.argv[1]](sys.argv[2])

