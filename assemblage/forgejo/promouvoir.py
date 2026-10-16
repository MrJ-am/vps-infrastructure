#!/usr/bin/env python3
"""Closed Forgejo preparation, activation and independent code-only rollback."""
import datetime,hashlib,importlib.util,json,os,pathlib,re,shlex,subprocess,sys,time,urllib.request
P=pathlib.Path
NIXPKGS='/nix/store/81s59zcy998ym4b36ayr29cjc9yhma5n-nixos-26.05.8639.c5c4a43b0e80/nixos'
EXPECTED='/nix/store/az22hgl8xp9sab6incdcnhbj7ljang78-nixos-system-nixos-26.05.8639.c5c4a43b0e80'
CONFIG_SHA='7a7fc7c90cc1cf662144020c5c5e5c55035c4afb60f25612d2bf8c159f1c1f81'
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

def unchanged():
 require(str(P('/run/current-system').resolve())==EXPECTED,'Génération de base modifiée: réinspecter')
 require(hashlib.sha256(P('/etc/nixos/configuration.nix').read_bytes()).hexdigest()==CONFIG_SHA,'Configuration concurrente: réinspecter')

def prepare():
 unchanged()
 base=D/'base.nix'
 if not base.exists():base.write_bytes(P('/etc/nixos/configuration.nix').read_bytes())
 require(hashlib.sha256(base.read_bytes()).hexdigest()==CONFIG_SHA,'Base invalide')
 configuration=D/'configuration.nix'
 configuration.write_text('{ ... }: { imports = [ (import ./payload/integration.nix { baseConfiguration = ./base.nix; }) ]; }\n')
 before=evaluate(base);after=evaluate(configuration)
 require(before['toplevel']==EXPECTED,'Évaluation de base différente du système installé')
 require(not after['errors'],'Assertions NixOS refusées')
 require(before['protected']==after['protected'],'Unité protégée modifiée')
 require(all(after['hosts'].get(k)==v for k,v in before['hosts'].items()),'Hôte existant modifié')
 require(set(after['hosts'])-set(before['hosts'])=={'git.mrg.am'},'Hôte nouveau inattendu')
 b=before['pg'];a=after['pg']
 for k in ('package','dataDir','settings','ident'):require(a[k]==b[k],'Configuration PostgreSQL historique modifiée: '+k)
 require(a['hba']=='local forgejo forgejo peer\n'+b['hba'],'Règles HBA non conservées')
 for k in ('databases','users'):require(set(a[k])==set(b[k])|{'forgejo'},'Registre SQL modifié: '+k)
 require(after['backups']==before['backups'],'Sauvegardes historiques modifiées')
 require(all(after['acmeTimers'].get(k)==v for k,v in before['acmeTimers'].items()),'Renouvellement TLS existant modifié')
 for k in before['system']:
  if k=='firewall':require(set(after['system'][k])==set(before['system'][k])|{2222},'Pare-feu inattendu')
  else:require(after['system'][k]==before['system'][k],'Socle modifié: '+k)
 with (D/'build.log').open('w') as log:
  p=subprocess.run(['nix-build','-I','nixpkgs='+NIXPKGS,'--no-out-link','--expr',
    '(import <nixpkgs/nixos/lib/eval-config.nix> {system="x86_64-linux";modules=['+str(configuration)+'];}).config.system.build.toplevel'],stdout=subprocess.PIPE,stderr=log,text=True,timeout=1800)
 require(p.returncode==0,'Construction refusée (build.log privé)')
 require(p.stdout.strip()==after['toplevel'],'Artefact différent de l’évaluation')
 require(P(after['toplevel']).is_dir(),'Artefact absent')
 cmd(['nix-store','--add-root',str(D/'candidate-root'),'--indirect','-r',after['toplevel']])
 backup_current()
 (D/'prepared.json').write_text(json.dumps({'revision':REV,'generation':after['toplevel'],'base':EXPECTED,'configuration_sha256':CONFIG_SHA,'preparedAt':time.time()},indent=2)+'\n')
 print(json.dumps({'forgejo':'prepared','revision':REV,'generation':after['toplevel'],'existingUnitsUnchanged':True,'oldVhostsUnchanged':True,'oldHbaPreserved':True,'activated':False}),flush=True)

def dns_ready():
 for resolver in ('https://dns.google/resolve','https://cloudflare-dns.com/dns-query'):
  for kind in ('A','AAAA'):
   req=urllib.request.Request(resolver+'?name=git.mrg.am&type='+kind,headers={'Accept':'application/dns-json'})
   with urllib.request.urlopen(req,timeout=20) as f:d=json.load(f)
   vals={v['data'] for v in d.get('Answer',[]) if v['type']==(1 if kind=='A' else 28)}
   require(d.get('Status')==0 and (vals=={'187.77.95.158'} if kind=='A' else not vals),'DNS git.mrg.am non prêt: activation arrêtée')

def rollback():
 # Idempotent return of configuration/code only. Never restore an old database.
 require((D/'base.nix').exists(),'Base de retour absente')
 current=P('/etc/nixos/configuration.nix').read_bytes()
 expected=('{ ... }: { imports = [ '+json.dumps(str(D/'configuration.nix'))+' ]; }\n').encode()
 require(current in (expected,(D/'base.nix').read_bytes()),'Configuration concurrente: retour automatique arrêté')
 P('/etc/nixos/configuration.nix').write_bytes((D/'base.nix').read_bytes())
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
 require(pids()==before_pids,'Processus protégé changé durant la sauvegarde')
 (D/'backup.json').write_text(json.dumps({k:v for k,v in report.items() if k!='fichiers_chiffres'},indent=2)+'\n')

def deploy():
 unchanged();dns_ready()
 prepared=json.loads((D/'prepared.json').read_text())
 require(prepared['revision']==REV and time.time()-prepared['preparedAt']<86400,'Préparation périmée')
 before_pids=pids()
 backup_current()
 unchanged();dns_ready()
 timer='forgejo-retour-'+REV[:12]
 cmd(['systemd-run','--unit='+timer,'--on-active=10min',sys.executable,str(D/'payload/promouvoir.py'),'retour',REV])
 entry='{ ... }: { imports = [ '+json.dumps(str(D/'configuration.nix'))+' ]; }\n'
 temp=P('/etc/nixos/.forgejo-configuration.tmp');temp.write_text(entry);temp.chmod(0o644);temp.replace('/etc/nixos/configuration.nix')
 try:
  cmd(['nix-env','--profile','/nix/var/nix/profiles/system','--set',prepared['generation']])
  cmd([prepared['generation']+'/bin/switch-to-configuration','switch'],timeout=360)
  require(str(P('/run/current-system').resolve())==prepared['generation'],'Activation différente du candidat')
  require(pids()==before_pids,'Un processus protégé a redémarré')
  cmd(['systemctl','is-active','forgejo','nginx','postgresql','sshd','mrjam-metier','kanidm'])
  for _ in range(60):
   try:
    with urllib.request.urlopen('https://git.mrg.am/api/v1/version',timeout=10) as r:
     require(r.status==200,'Forgejo inaccessible');version=json.load(r)
    break
   except Exception:time.sleep(2)
  else:raise RuntimeError('HTTPS Forgejo non disponible')
  require(version['version'].startswith('16.0.3'),'Version inattendue')
  cmd(['systemctl','stop',timer+'.timer'])
  (D/'deployed.json').write_text(json.dumps({'revision':REV,'generation':prepared['generation'],'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat(),'protectedPidsUnchanged':True},indent=2)+'\n')
  print(json.dumps({'forgejo':'deployed','revision':REV,'generation':prepared['generation'],'https':True,'protectedPidsUnchanged':True}),flush=True)
 except Exception:
  rollback();raise

if __name__=='__main__':
 os.umask(0o077)
 phase,REV=sys.argv[1:];require(os.geteuid()==0 and re.fullmatch('[0-9a-f]{40}',REV),'Contexte invalide')
 D=P('/root/mrjam-corrections/forgejo')/REV
 require(P(__file__).resolve()==D/'payload/promouvoir.py','Emplacement invalide')
 require(phase in ('preparer','deployer','retour'),'Opération inconnue')
 try:{'preparer':prepare,'deployer':deploy,'retour':rollback}[phase]()
 except Exception as e:
  print(json.dumps({'forgejo':'stopped','phase':phase,'reason':str(e),'privateLog':str(D/'operation-private.log')}),flush=True)
  sys.exit(1)
