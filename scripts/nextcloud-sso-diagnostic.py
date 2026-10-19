"""Read-only metadata for the Nextcloud / Kanidm integration; no credentials."""
import hashlib,json,pathlib,subprocess

def run(args):
    p=subprocess.run(args,capture_output=True,text=True,timeout=180)
    if p.returncode: raise RuntimeError(p.stderr[-2500:])
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
 'status':json.loads(run(['runuser','-u','nextcloud','--','nextcloud-occ','status','--output=json'])),
 'apps':json.loads(run(['runuser','-u','nextcloud','--','nextcloud-occ','app:list','--output=json']))}
result['accounts']={'local':int(sql('SELECT count(*) FROM oc_users')),
 'admins':int(sql("SELECT count(*) FROM oc_group_user WHERE gid='admin'")),
 'filecache':int(sql('SELECT count(*) FROM oc_filecache')),
 'shares':int(sql('SELECT count(*) FROM oc_share'))}
result['protectedPids']={n:run(['systemctl','show',n,'-p','MainPID','--value']) for n in ['postgresql','kanidm','mrjam-metier','forgejo','sshd']}
print(json.dumps(result,sort_keys=True))
