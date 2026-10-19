"""Read-only metadata for the Nextcloud / Kanidm integration; no credentials."""
import hashlib,json,pathlib,re,subprocess

def run(args):
    p=subprocess.run(args,capture_output=True,text=True,timeout=180)
    if p.returncode: raise RuntimeError('Command '+str(args[:5])+' failed: '+p.stderr[-2000:]+' stdout: '+p.stdout[:500])
    return p.stdout.strip()

expression='''let e=import <nixpkgs/nixos/lib/eval-config.nix> {system="x86_64-linux";modules=[/etc/nixos/configuration.nix];}; c=e.config; in {
  generation=toString c.system.build.toplevel;
  nextcloud={package=toString c.services.nextcloud.package;php=toString c.services.nextcloud.phpPackage;apps=builtins.mapAttrs (_: a: toString a) c.services.nextcloud.extraApps;};
  oidc={package=toString e.pkgs.nextcloud34Packages.apps.user_oidc;name=e.pkgs.nextcloud34Packages.apps.user_oidc.name;};
  kanidm=toString c.services.kanidm.package;
  postgres=toString c.services.postgresql.finalPackage;
}'''
def sql(query):
    return run(['runuser','-u','postgres','--','psql','-XAtq','-d','nextcloud','-c',query])

result={'configuration':json.loads(run(['nix-instantiate','--eval','--strict','--json','--expr',expression])),
 'entrySha256':hashlib.sha256(pathlib.Path('/etc/nixos/configuration.nix').read_bytes()).hexdigest(),
 'entry':pathlib.Path('/etc/nixos/configuration.nix').read_text(),
 'status':json.loads(run(['runuser','-u','nextcloud','--','env','-i','PATH=/run/current-system/sw/bin','USER=nextcloud','HOME=/var/lib/nextcloud','nextcloud-occ','status','--output=json'])),
 'apps':json.loads(run(['runuser','-u','nextcloud','--','env','-i','PATH=/run/current-system/sw/bin','USER=nextcloud','HOME=/var/lib/nextcloud','nextcloud-occ','app:list','--output=json']))}
result['accounts']={'local':int(sql('SELECT count(*) FROM oc_users')),
 'admins':int(sql("SELECT count(*) FROM oc_group_user WHERE gid='admin'")),
 'filecache':int(sql('SELECT count(*) FROM oc_filecache')),
 'shares':int(sql('SELECT count(*) FROM oc_share'))}
result['protectedPids']={n:run(['systemctl','show',n,'-p','MainPID','--value']) for n in ['postgresql','kanidm','mrjam-metier','forgejo','sshd']}
result['accountMetadata']=json.loads(sql("SELECT json_agg(json_build_object('uid',u.uid,'admin',EXISTS(SELECT 1 FROM oc_group_user g WHERE g.uid=u.uid AND g.gid='admin'),'lastLogin',(SELECT configvalue FROM oc_preferences p WHERE p.userid=u.uid AND p.appid='login' AND p.configkey='lastLogin'),'tokens',(SELECT count(*) FROM oc_authtoken t WHERE t.uid=u.uid))) FROM oc_users u"))
without_contacts='''let base=import <nixpkgs/nixos/lib/eval-config.nix> {system="x86_64-linux";modules=[/etc/nixos/configuration.nix];}; e=import <nixpkgs/nixos/lib/eval-config.nix> {system="x86_64-linux";modules=[/etc/nixos/configuration.nix ({lib,...}: {services.nextcloud.extraApps=lib.mkForce (builtins.removeAttrs base.config.services.nextcloud.extraApps ["contacts"]);})];}; in toString e.config.system.build.toplevel'''
result['evaluatedWithoutPendingContacts']=json.loads(run(['nix-instantiate','--eval','--strict','--json','--expr',without_contacts]))
result['installedGeneration']=str(pathlib.Path('/run/current-system').resolve())
# The failed command was switch-to-configuration, before client provisioning.
# Only its fixed operator error lines are exported, never arbitrary private logs.
log=pathlib.Path('/root/mrjam-corrections/nextcloud-sso/095ee47d56db59347b74db4a8bd7c391bda92671/command-private.log')
if log.exists():
    result['switchErrors']=[line[:700] for line in log.read_text().splitlines() if re.search(r'error|failed|not found|Traceback|Error|No such|Permission|cannot|insecure|PATH|undefined|unbound',line)][:25]
journal=run(['journalctl','-u','nextcloud-setup.service','--since','2026-10-19 21:42:00 UTC','--no-pager','-o','cat','-n','80'])
result['setupDiagnostic']=journal.splitlines()[-65:]
result['returnTimers']=run(['systemctl','list-timers','--all','--no-legend','nextcloud-sso-return-*'])
print(json.dumps(result,sort_keys=True))
