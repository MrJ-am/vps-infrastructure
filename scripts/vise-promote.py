#!/usr/bin/env python3
"""Closed ViSe promotion. Preserve all existing data; rollback code/config only."""
import hashlib,json,os,pathlib,shutil,subprocess,sys,tarfile,time,urllib.request,importlib.util,tempfile
P=pathlib.Path
NIX='/nix/store/81s59zcy998ym4b36ayr29cjc9yhma5n-nixos-26.05.8639.c5c4a43b0e80/nixos'
ROOT=P(__file__).resolve().parents[1]

def run(args,**kw):
 return subprocess.check_output([str(x) for x in args],text=True,**kw).strip()
def check(ok,msg):
 if not ok:raise RuntimeError(msg)
def main():
 target=json.loads((ROOT/'assemblage/vise/target.json').read_text());sha=target['sha256']
 archive=ROOT/'vise-portable.tar.gz'
 check(hashlib.sha256(archive.read_bytes()).hexdigest()==sha,'Artifact mismatch')
 check(os.getuid()==0,'Root required')
 entry=P('/etc/nixos/configuration.nix');base=entry.read_bytes()
 check(b'vise-hosting' not in base,'ViSe already declared; inspect before upgrading')
 generation=P('/run/current-system').resolve()
 check(str(generation)==target['expectedGeneration'],'Baseline generation changed')
 protect=['postgresql','mrjam-metier','kanidm','forgejo','sshd']
 before={s:run(['systemctl','show',s,'-p','MainPID','--value']) for s in protect}
 check(all(v!='0' for v in before.values()),'Protected service inactive')
 for t in ('A','AAAA'):
  data=json.load(urllib.request.urlopen('https://dns.google/resolve?name=vise.mrj.am&type='+t))
  answers={a['data'] for a in data.get('Answer',[]) if a['type']==(1 if t=='A' else 28)}
  check(answers==({'187.77.95.158'} if t=='A' else set()),'DNS precondition failed')
 stage_parent=P('/root/vise-promotion');stage_parent.mkdir(exist_ok=True,mode=0o700)
 stage=P(tempfile.mkdtemp(prefix=sha[:12]+'-',dir=stage_parent))
 (stage/'base.nix').write_bytes(base)
 # Capture public infrastructure settings, never passwords or account data.
 expr='let c=(import <nixpkgs/nixos> {configuration=/etc/nixos/configuration.nix;}).config; in {existingBackupDatabases=c.services.postgresqlBackup.databases;backupRecipient=c.services.vision.backupRecipient;}'
 settings=json.loads(run(['nix-instantiate','-I','nixpkgs='+NIX,'--eval','--strict','--json','--expr',expr]))
 check(settings['backupRecipient'].startswith(('age1','ssh-')),'Missing owner backup recipient')
 target.update(settings)
 target['baselineConfiguration']='/etc/nixos/configuration.nix'
 # Reuse the existing isolated restore mechanism against the observed baseline,
 # as other promotion operators do; its algorithms/SQL remain unchanged.
 spec=importlib.util.spec_from_file_location('vise_backup',ROOT/'scripts/monolithe-sauvegarde.py')
 backup=importlib.util.module_from_spec(spec);spec.loader.exec_module(backup)
 backup.GENERATION=str(generation)
 backup.main(target['sourceRevision'])
 release=P('/var/lib/vise/releases')/sha;release.mkdir(parents=True,exist_ok=True)
 for parent in (release.parent.parent, release.parent, release):parent.chmod(0o755)
 with tarfile.open(archive) as a:
  for m in a.getmembers():
   check(not m.issym() and not m.islnk() and not P(m.name).is_absolute() and '..' not in P(m.name).parts,'Unsafe archive')
  a.extractall(release,filter='data')
 for p in release.rglob('*'):p.chmod(0o755 if p.is_dir() or p.name=='server' else 0o644)
 q=json.loads((release/'qualification.json').read_text())
 check(q['apiTests']==9 and hashlib.sha256((release/'server').read_bytes()).hexdigest()==q['serverSha256'],'Unqualified server')
 shutil.copy(ROOT/'assemblage/vise/module.nix',stage/'module.nix')
 shutil.copy(ROOT/'assemblage/vise/backup.sh',stage/'backup.sh')
 shutil.copy(ROOT/'assemblage/vise/provision.sh',stage/'provision.sh')
 (stage/'target.json').write_text(json.dumps(target))
 (stage/'candidate.nix').write_text('{ imports = [ /etc/nixos/configuration.nix ./module.nix { systemd.services.postgresql = { restartIfChanged = false; reloadIfChanged = false; stopIfChanged = false; }; } ]; }\n')
 candidate=run(['nix-build','<nixpkgs/nixos>','-A','system','-I','nixpkgs='+NIX,'-I','nixos-config='+str(stage/'candidate.nix'),'--out-link',stage/'result'])
 check(candidate.startswith('/nix/store/'),'Invalid candidate')
 rollback=stage/'rollback.sh'
 rollback.write_text('#!/bin/sh\nset -eu\ncp '+str(stage/'base.nix')+' /etc/nixos/configuration.nix\n'+str(generation)+'/bin/switch-to-configuration test\nnix-env -p /nix/var/nix/profiles/system --set '+str(generation)+'\n'+str(generation)+'/bin/switch-to-configuration boot\n')
 rollback.chmod(0o700)
 run(['systemd-run','--unit=vise-return','--on-active=12m',rollback])
 try:
  switched=subprocess.run([candidate+'/bin/switch-to-configuration','test'])
  check(switched.returncode in (0,4),'Configuration activation failed')
  # PostgreSQL17 marks hba_file as postmaster: reload cannot change its path.
  # The shared cluster is restarted once; no dataDir or major version changes.
  subprocess.run(['systemctl','--job-mode=ignore-dependencies','restart','postgresql.service'],check=True)
  subprocess.run(['systemctl','reset-failed','vise.service'],check=True)
  subprocess.run(['systemctl','restart','vise.service'],check=True)
  for _ in range(60):
   try:
    with urllib.request.urlopen('https://vise.mrj.am/api/health',timeout=10) as r:
     if r.status==200:break
   except Exception:time.sleep(5)
  else:raise RuntimeError('HTTPS health failed')
  after={s:run(['systemctl','show',s,'-p','MainPID','--value']) for s in protect}
  check(all(before[s]==after[s] for s in protect if s!='postgresql'),'Protected application restarted unexpectedly: '+','.join(s for s in protect if s!='postgresql' and before[s]!=after[s]))
  check(after['postgresql']!='0','Shared PostgreSQL unavailable')
  # Authentication into other databases must be rejected by peer/HBA.
  denied=subprocess.run(['runuser','-u','etp_carnet','--','psql','-h','/run/postgresql','-U','etp_carnet','-d','postgres','-c','SELECT 1'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  check(denied.returncode!=0,'Cross-database access not rejected')
  subprocess.run(['systemctl','start','vise-backup.service'],check=True)
  check(run(['systemctl','show','vise-backup','-p','Result','--value'])=='success','Backup failed')
  # Persist an additive wrapper, preserving the original module byte for byte.
  persisted=P('/etc/nixos/vise-hosting');persisted.mkdir(mode=0o700)
  for name in ('module.nix','backup.sh','provision.sh'):shutil.copy(stage/name,persisted/name)
  target['baselineConfiguration']='/etc/nixos/vise-base.nix'
  (persisted/'target.json').write_text(json.dumps(target))
  shutil.copy(stage/'base.nix',P('/etc/nixos/vise-base.nix'))
  entry.write_text('{ imports = [ ./vise-base.nix ./vise-hosting/module.nix ]; }\n')
  subprocess.run(['nix-env','-p','/nix/var/nix/profiles/system','--set',candidate],check=True)
  subprocess.run([candidate+'/bin/switch-to-configuration','boot'],check=True)
  run(['systemctl','stop','vise-return.timer'])
  report={'domain':'https://vise.mrj.am','artifactSha256':sha,'generation':candidate,'sharedPostgres':True,'separateDatabase':'etp_carnet','protectedApplicationPidsPreserved':True,'sharedPostgresRestartedForHba':True,'httpsHealth':True,'encryptedBackup':True}
  (stage/'result.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
 except BaseException:
  subprocess.run([str(rollback)],check=False)
  subprocess.run(['systemctl','stop','vise-return.timer'],check=False)
  raise
if __name__=='__main__':main()
