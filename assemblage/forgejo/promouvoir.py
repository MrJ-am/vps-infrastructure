#!/usr/bin/env python3
"""Closed Forgejo preparation, activation and independent code-only rollback."""
import datetime,hashlib,importlib.util,json,os,pathlib,re,shlex,subprocess,sys,time,urllib.request,uuid
P=pathlib.Path
NIXPKGS='/nix/store/81s59zcy998ym4b36ayr29cjc9yhma5n-nixos-26.05.8639.c5c4a43b0e80/nixos'
EXPECTED='/nix/store/6791pn34plb531ygfxfyk9riq79x10d0-nixos-system-nixos-26.05.8639.c5c4a43b0e80'
CONFIG_SHA='83f9b487c1060986b6de9a018b1f69737fe35955d3c2d8bde48a25fa8b7ef51a'
RUNTIME_BASE='/root/mrjam-corrections/forgejo/95b33d038c5652b4d23d30b8ccee21b8989f06c8/base.nix'
PROTECTED=('sshd','mrjam-metier','kanidm','vision-embeddings','phpfpm-nextcloud','redis-nextcloud')

def require(b,msg):
 if not b:raise RuntimeError(msg)

def cmd(args,timeout=180,input=None):
 p=subprocess.run([str(a) for a in args],input=input,capture_output=True,text=True,timeout=timeout)
 if p.returncode:
  # Commands can touch private data; retain diagnostics locally, print no bodies.
  with (D/'operation-private.log').open('a') as f:f.write(p.stderr+'\n'+p.stdout+'\n')
  detail=''
  if P(str(args[0])).name=='nix-instantiate':
   errors=re.findall(r'(?m)^\s*error: ([^\n]+)',p.stderr)
   detail=': '+errors[-1][:300] if errors else ''
  raise RuntimeError('Commande refusée: '+P(str(args[0])).name+detail+' (voir operation-private.log sur le VPS)')
 return p.stdout.strip()

def evaluate(path):
 expression='''let e=import <nixpkgs/nixos/lib/eval-config.nix> {system="x86_64-linux";modules=[PATH];};c=e.config; in {
 toplevel=toString c.system.build.toplevel;
 errors=map (a: a.message) (builtins.filter (a: !a.assertion) c.assertions);
 units=builtins.mapAttrs (n: u: u.text) c.systemd.units;
 protected=builtins.listToAttrs (map (n: {name=n;value=c.systemd.units."${n}.service".text;}) PROTECTED);
 hosts=builtins.mapAttrs (n: v: builtins.toJSON (e.pkgs.lib.filterAttrs (k: value: (builtins.tryEval value).success) v)) c.services.nginx.virtualHosts;
 pg={package=toString c.services.postgresql.finalPackage;dataDir=c.services.postgresql.dataDir;settings=builtins.removeAttrs c.services.postgresql.settings ["hba_file" "ident_file"];ident=c.services.postgresql.identMap;hba=c.services.postgresql.authentication;databases=c.services.postgresql.ensureDatabases;users=map (u: u.name) c.services.postgresql.ensureUsers;};
 system={kernel=toString c.boot.kernelPackages.kernel;filesystems=builtins.mapAttrs (n: fs: e.pkgs.lib.getAttrs ["device" "fsType" "options" "neededForBoot" "autoResize" "autoFormat"] fs) c.fileSystems;network=builtins.mapAttrs (n: file: toString file.source) (e.pkgs.lib.filterAttrs (n: file: e.pkgs.lib.hasPrefix "systemd/network/" n) c.environment.etc);firewall=c.networking.firewall.allowedTCPPorts;openssh=c.services.openssh.settings;};
 backups=c.services.postgresqlBackup.databases;
 acmeTimers=builtins.mapAttrs (n: unit: unit.text) (e.pkgs.lib.filterAttrs (n: unit: e.pkgs.lib.hasPrefix "acme-renew-" n && e.pkgs.lib.hasSuffix ".timer" n) c.systemd.units);
 forgejo={enable=c.services.forgejo.enable;package=toString c.services.forgejo.package;root=c.services.forgejo.settings.server.ROOT_URL;};
}'''.replace('PATH',str(path)).replace('PROTECTED','[ '+' '.join(json.dumps(n) for n in PROTECTED)+' ]')
 return json.loads(cmd(['nix-instantiate','-I','nixpkgs='+NIXPKGS,'--eval','--strict','--json','--expr',expression],timeout=300))

def pids():return {n:cmd(['systemctl','show',n,'-p','MainPID','--value']) for n in PROTECTED}

def executable_hash(pid):
 if pid=='0':return None
 require(pid.isdigit() and int(pid)>0,'Processus actif attendu')
 with open('/proc/'+pid+'/exe','rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def pg_dependency(unit,seen=None):
 seen=set() if seen is None else seen
 if unit in seen or len(seen)>100:return False
 if unit in ('postgresql.service','postgresql-setup.service'):return True
 seen.add(unit)
 deps=cmd(['systemctl','show',unit,'-p','Requires','-p','BindsTo','--value']).split()
 return any(pg_dependency(dep,seen) for dep in deps if dep.endswith('.service'))

def qualify_return():
 marker=D/'return-probe.json'
 marker.unlink(missing_ok=True)
 name='forgejo-retour-check-'+REV[:12]+'-'+uuid.uuid4().hex[:6]
 cmd(['systemd-run','--unit='+name,'--collect','--on-active=2s',sys.executable,str(D/'payload/promouvoir.py'),'temoin-retour',REV])
 for _ in range(40):
  if marker.exists():break
  time.sleep(.25)
 require(marker.exists() and json.loads(marker.read_text())['base']==EXPECTED,'Témoin indépendant non exécuté')

def return_probe():
 require(hashlib.sha256((D/'base.nix').read_bytes()).hexdigest()==CONFIG_SHA,'Base de retour invalide')
 require(P(EXPECTED+'/bin/switch-to-configuration').is_file(),'Génération de retour absente')
 (D/'return-probe.json').write_text(json.dumps({'base':EXPECTED,'revision':REV,'executedBy':'systemd-timer'})+'\n')

def unchanged():
 require(str(P('/run/current-system').resolve())==EXPECTED,'Génération de base modifiée: réinspecter')
 require(hashlib.sha256(P('/etc/nixos/configuration.nix').read_bytes()).hexdigest()==CONFIG_SHA,'Configuration concurrente: réinspecter')

def prepare():
 unchanged()
 base=D/'base.nix'
 if not base.exists():base.write_bytes(P('/etc/nixos/configuration.nix').read_bytes())
 require(hashlib.sha256(base.read_bytes()).hexdigest()==CONFIG_SHA,'Base invalide')
 configuration=D/'configuration.nix'
 configuration.write_text('{ ... }: { imports = [ (import ./payload/integration.nix { baseConfiguration = '+RUNTIME_BASE+'; timerConfiguration = ./base.nix; kanidmApi = ./payload/kanidm-api-privee.py; }) ]; }\n')
 before=evaluate(base);after=evaluate(configuration)
 require(before['toplevel']==EXPECTED,'Évaluation de base différente du système installé')
 require(not after['errors'],'Assertions NixOS refusées')
 require(before['protected']==after['protected'],'Unité protégée modifiée')
 require(all(after['hosts'].get(k)==v for k,v in before['hosts'].items()),'Hôte existant modifié')
 require(set(after['hosts'])==set(before['hosts']),'Registre des hôtes modifié')
 require(after['forgejo']==before['forgejo'],'Paramètres Forgejo modifiés')
 allowed={'forgejo.service','forgejo-bootstrap.service','forgejo-identity.service','forgejo-account.service','forgejo-backup.service','forgejo-backup-qualification.service'}
 require((set(after['units']) ^ set(before['units'])) <= allowed,'Registre des unités modifié')
 require(all(after['units'].get(n)==v for n,v in before['units'].items() if n not in allowed),'Unité hors sauvegarde Forgejo modifiée')
 b=before['pg'];a=after['pg']
 for k in ('package','dataDir','settings','ident'):require(a[k]==b[k],'Configuration PostgreSQL historique modifiée: '+k)
 require(a['hba']==b['hba'],'Règles HBA non conservées')
 for k in ('databases','users'):require(set(a[k])==set(b[k]),'Registre SQL modifié: '+k)
 require(after['backups']==before['backups'],'Sauvegardes historiques modifiées')
 require(all(after['acmeTimers'].get(k)==v for k,v in before['acmeTimers'].items()),'Renouvellement TLS existant modifié')
 for k in before['system']:
  if k=='firewall':require(set(after['system'][k])==set(before['system'][k]),'Pare-feu inattendu')
  else:require(after['system'][k]==before['system'][k],'Socle modifié: '+k)
 with (D/'build.log').open('w') as log:
  p=subprocess.run(['nix-build','-I','nixpkgs='+NIXPKGS,'--no-out-link','--expr',
    '(import <nixpkgs/nixos/lib/eval-config.nix> {system="x86_64-linux";modules=['+str(configuration)+'];}).config.system.build.toplevel'],stdout=subprocess.PIPE,stderr=log,text=True,timeout=1800)
 require(p.returncode==0,'Construction refusée (build.log privé)')
 require(p.stdout.strip()==after['toplevel'],'Artefact différent de l’évaluation')
 require(P(after['toplevel']).is_dir(),'Artefact absent')
 cmd(['nix-store','--add-root',str(D/'candidate-root'),'--indirect','-r',after['toplevel']])
 cmd(['nix-store','--add-root',str(D/'base-root'),'--indirect','-r',EXPECTED])
 cmd(['nix-store','--add-root',str(D/'return-python-root'),'--indirect','-r',str(P(sys.executable).resolve().parents[1])])
 qualify_return()
 backup_current()
 (D/'prepared.json').write_text(json.dumps({'revision':REV,'generation':after['toplevel'],'base':EXPECTED,'configuration_sha256':CONFIG_SHA,'preparedAt':time.time()},indent=2)+'\n')
 print(json.dumps({'forgejo':'prepared','revision':REV,'generation':after['toplevel'],'existingUnitsUnchanged':True,'oldVhostsUnchanged':True,'oldHbaPreserved':True,'activated':False}),flush=True)

def dns_ready():
 for resolver in ('https://dns.google/resolve','https://cloudflare-dns.com/dns-query'):
  for kind in ('A','AAAA'):
   req=urllib.request.Request(resolver+'?name=forge.mrj.am&type='+kind,headers={'Accept':'application/dns-json'})
   with urllib.request.urlopen(req,timeout=20) as f:d=json.load(f)
   vals={v['data'] for v in d.get('Answer',[]) if v['type']==(1 if kind=='A' else 28)}
   require(d.get('Status')==0 and (vals=={'187.77.95.158'} if kind=='A' else not vals),'DNS forge.mrj.am non prêt: activation arrêtée')

def rollback():
 # Idempotent return of configuration/code only. Never restore an old database.
 require((D/'base.nix').exists(),'Base de retour absente')
 current=P('/etc/nixos/configuration.nix').read_bytes()
 expected=('{ ... }: { imports = [ '+json.dumps(str(D/'configuration.nix'))+' ]; }\n').encode()
 require(current in (expected,(D/'base.nix').read_bytes()),'Configuration concurrente: retour automatique arrêté')
 cmd(['systemctl','stop','forgejo-retour-'+REV[:12]+'.timer'])
 temp=P('/etc/nixos/.forgejo-return.tmp');temp.write_bytes((D/'base.nix').read_bytes());temp.chmod(0o644);temp.replace('/etc/nixos/configuration.nix')
 cmd(['nix-env','--profile','/nix/var/nix/profiles/system','--set',EXPECTED])
 cmd([EXPECTED+'/bin/switch-to-configuration','switch'],timeout=300)
 require(str(P('/run/current-system').resolve())==EXPECTED,'Retour non activé')
 print(json.dumps({'forgejo':'rolled-back','dataRestored':False,'generation':EXPECTED}),flush=True)

def backup_current():
 before_pids=pids()
 spec=importlib.util.spec_from_file_location('forgejo_backup_existing',D/'payload/backup-existing.py')
 backup=importlib.util.module_from_spec(spec);spec.loader.exec_module(backup)
 backup.GENERATION=EXPECTED
 try:report=backup.main(REV,sqlite_reprise={'log-native':'/var/lib/mrjam-metier/log/sessions.sqlite'})
 except Exception:raise RuntimeError('Sauvegarde actuelle arrêtée à l’étape '+backup.ETAPE) from None
 cmd(['systemctl','start','forgejo-backup-qualification.service'],timeout=300)
 require(cmd(['systemctl','show','forgejo-backup-qualification','-p','Result','--value'])=='success','Sauvegarde Forgejo restaurée isolément refusée')
 cmd(['systemctl','start','mrjam-sauvegarde.service'],timeout=300)
 require(cmd(['systemctl','show','mrjam-sauvegarde.service','-p','Result','--value'])=='success','Sauvegarde Native courante refusée')
 require(pids()==before_pids,'Processus protégé changé durant la sauvegarde')
 (D/'backup.json').write_text(json.dumps({k:v for k,v in report.items() if k!='fichiers_chiffres'},indent=2)+'\n')

def deploy():
 unchanged();dns_ready()
 prepared=json.loads((D/'prepared.json').read_text())
 require(prepared['revision']==REV and time.time()-prepared['preparedAt']<86400,'Préparation périmée')
 before_pids=pids()
 before_pg=cmd(['systemctl','show','postgresql','-p','MainPID','--value'])
 binaries={n:executable_hash(pid) for n,pid in before_pids.items()}
 dependents={n:pg_dependency(n+'.service') for n in PROTECTED}
 backup_current()
 qualify_return()
 unchanged();dns_ready()
 timer='forgejo-retour-'+REV[:12]
 cmd(['systemd-run','--unit='+timer,'--on-active=10min',sys.executable,str(D/'payload/promouvoir.py'),'retour',REV])
 entry='{ ... }: { imports = [ '+json.dumps(str(D/'configuration.nix'))+' ]; }\n'
 temp=P('/etc/nixos/.forgejo-configuration.tmp');temp.write_text(entry);temp.chmod(0o644);temp.replace('/etc/nixos/configuration.nix')
 try:
  cmd(['nix-env','--profile','/nix/var/nix/profiles/system','--set',prepared['generation']])
  cmd([prepared['generation']+'/bin/switch-to-configuration','switch'],timeout=360)
  require(str(P('/run/current-system').resolve())==prepared['generation'],'Activation différente du candidat')
  after_pids=pids();after_pg=cmd(['systemctl','show','postgresql','-p','MainPID','--value'])
  restarted=[]
  for name,pid in after_pids.items():
   require(executable_hash(pid)==binaries[name],'Code protégé modifié: '+name)
   if pid!=before_pids[name]:
    require(before_pg!=after_pg and dependents[name],'Redémarrage hors dépendance PostgreSQL: '+name)
    restarted.append(name)
  cmd(['systemctl','is-active','forgejo','nginx','postgresql','sshd','mrjam-metier','kanidm'])
  cmd(['systemctl','start','forgejo-account'])
  require(cmd(['systemctl','show','forgejo-account','-p','Result','--value'])=='success','Rattachement administrateur refusé')
  require(cmd(['systemctl','show','forgejo-identity','-p','Result','--value'])=='success','Client Kanidm refusé')
  admin=cmd(['runuser','-u','forgejo','--','psql','-XAtq','-h','/run/postgresql','-d','forgejo','-c','SELECT count(*) FROM "user" WHERE is_admin;'])
  require(int(admin)>0,'Aucun administrateur Forgejo')
  for _ in range(60):
   try:
    with urllib.request.urlopen('https://forge.mrj.am/user/login',timeout=10) as r:
     require(r.status==200 and b'/user/oauth2/Kanidm' in r.read(),'Connexion HTTPS Forgejo inaccessible')
    break
   except Exception:time.sleep(2)
  else:raise RuntimeError('HTTPS Forgejo non disponible')
  cmd(['systemctl','stop',timer+'.timer'])
  (D/'deployed.json').write_text(json.dumps({'revision':REV,'generation':prepared['generation'],'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat(),'protectedCodeUnchanged':True,'postgresRestarted':before_pg!=after_pg,'dependencyRestarts':restarted},indent=2)+'\n')
  print(json.dumps({'forgejo':'deployed','revision':REV,'generation':prepared['generation'],'https':True,'protectedCodeUnchanged':True,'postgresRestarted':before_pg!=after_pg,'dependencyRestarts':restarted}),flush=True)
 except Exception:
  rollback();raise

if __name__=='__main__':
 os.umask(0o077)
 phase,REV=sys.argv[1:];require(os.geteuid()==0 and re.fullmatch('[0-9a-f]{40}',REV),'Contexte invalide')
 D=P('/root/mrjam-corrections/forgejo')/REV
 require(P(__file__).resolve()==D/'payload/promouvoir.py','Emplacement invalide')
 require(phase in ('preparer','deployer','retour','temoin-retour'),'Opération inconnue')
 try:{'preparer':prepare,'deployer':deploy,'retour':rollback,'temoin-retour':return_probe}[phase]()
 except Exception as e:
  print(json.dumps({'forgejo':'stopped','phase':phase,'reason':str(e),'privateLog':str(D/'operation-private.log')}),flush=True)
  sys.exit(1)
