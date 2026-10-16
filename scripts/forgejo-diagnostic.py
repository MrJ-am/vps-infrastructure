#!/usr/bin/env python3
"""Read-only, allowlisted system metadata for the Forgejo integration."""
import json, pathlib, subprocess, hashlib

def cmd(args, timeout=180):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=timeout).stdout.strip()

NIXPKGS='/nix/store/81s59zcy998ym4b36ayr29cjc9yhma5n-nixos-26.05.8639.c5c4a43b0e80/nixos'
EXPR='''let e=import <nixpkgs/nixos/lib/eval-config.nix> {system="x86_64-linux";modules=[/etc/nixos/configuration.nix];}; c=e.config; in {
 kanidm={package=toString c.services.kanidm.package;configFile=c.services.kanidm.server.configFile or null;};
 forgejoAuthentication={internal=c.services.forgejo.settings.service.ENABLE_INTERNAL_SIGNIN or true;basic=c.services.forgejo.settings.service.ENABLE_BASIC_AUTHENTICATION or true;quotaEnabled=c.services.forgejo.settings.quota.ENABLED or false;quotaTotal=c.services.forgejo.settings."quota.default".TOTAL or "-1";maxRepositories=c.services.forgejo.settings.repository.MAX_CREATION_LIMIT or (-1);};
 forgejo=c.services.forgejo.enable; forgejoVersion=e.pkgs.forgejo.version; pandocVersion=e.pkgs.pandoc.version;
 postgres={package=toString c.services.postgresql.finalPackage;dataDir=c.services.postgresql.dataDir;authentication=c.services.postgresql.authentication;identMap=c.services.postgresql.identMap;};
 domains=builtins.attrNames c.services.nginx.virtualHosts;
 acmeEmail=c.security.acme.defaults.email;
 recipient=c.services.vision.backupRecipient;
 firewall=c.networking.firewall.allowedTCPPorts;
 ssh=c.services.openssh.ports;
}'''
r={'generation':cmd(['readlink','-f','/run/current-system']),
   'configuration_sha256':hashlib.sha256(pathlib.Path('/etc/nixos/configuration.nix').read_bytes()).hexdigest(),
   'flake_present':pathlib.Path('/etc/nixos/flake.nix').exists(),
   'configuration':json.loads(cmd(['nix-instantiate','-I','nixpkgs='+NIXPKGS,'--eval','--strict','--json','--expr',EXPR])),
   'listeners':cmd(['ss','-lnt']),
   'services':{n:cmd(['systemctl','show',n,'--property=ActiveState,MainPID','--value']) for n in ('nginx','postgresql','sshd','mrjam-metier','kanidm','vision-embeddings','phpfpm-nextcloud')},
   'dependencies':{n:cmd(['systemctl','show',n,'--property=Requires,BindsTo','--value']) for n in ('sshd','mrjam-metier','kanidm','vision-embeddings','phpfpm-nextcloud','redis-nextcloud')},
   'forgejo_paths_present':{p:pathlib.Path(p).exists() for p in ('/var/lib/forgejo','/var/backup/forgejo')}}

r['forgejo_preparation_errors']=[]
for log in sorted(pathlib.Path('/root/mrjam-corrections/forgejo').glob('*/*.log')):
    if log.name not in ('operation-private.log','build.log') or log.stat().st_size>1048576:continue
    # Error summaries only: no eval output, SQL data, journal or arbitrary file.
    text=log.read_text()
    errors=__import__('re').findall(r'(?m)^\s*(?:error:|curl:|tar:|cp:|mv:) ([^\n]+)',text)
    r['forgejo_preparation_errors'].append({'revision':log.parent.name,'log':log.name,'errors':[e[:500] for e in errors[-12:]]})

r['forgejoUnits']={n:cmd(['systemctl','show',n,'--property=ActiveState,SubState,Result,ExecMainStatus','--value']) for n in ('forgejo','forgejo-identity','forgejo-account','forgejo-backup','forgejo-backup-qualification')}
journal=cmd(['journalctl','-u','forgejo-backup-qualification','-n','70','--no-pager','-o','cat'])
r['backupErrors']=[line[:400] for line in journal.splitlines() if any(token in line for token in ('RuntimeError:','Error:','Permission denied','not found','cannot ','could not ','failed:'))]
secret=pathlib.Path('/var/lib/forgejo-bootstrap/initial-admin.txt')
if secret.exists():
    stat=secret.stat();r['bootstrapSecretMetadata']={'uid':stat.st_uid,'mode':oct(stat.st_mode & 0o777),'parentMode':oct(secret.parent.stat().st_mode & 0o777),'contentRead':False}
r['forgejoBackupTimer']=cmd(['systemctl','show','forgejo-backup.timer','--property=ActiveState,NextElapseUSecRealtime','--value'])
r['forgejoEncryptedBackupPairs']=sum(1 for p in pathlib.Path('/var/backup/forgejo').glob('*.tar.age') if pathlib.Path(str(p)+'.key.age').is_file())
r['kanidmExecStart']=cmd(['systemctl','show','kanidm','--property=ExecStart','--value'])
r['forgejoAccounts']=json.loads(cmd(['runuser','-u','postgres','--','psql','-XAtq','-d','forgejo','-c', "SELECT json_agg(json_build_object('name',name,'admin',is_admin,'loginType',login_type,'loginSource',login_source,'mustChangePassword',must_change_password)) FROM \"user\";"]))
identity=pathlib.Path('/var/lib/forgejo-identity/client.json')
if identity.exists():
    stat=identity.stat();r['oidcSecretMetadata']={'uid':stat.st_uid,'mode':oct(stat.st_mode & 0o777),'parentMode':oct(identity.parent.stat().st_mode & 0o777),'contentRead':False}
r['temporarySsoProbeTokens']=int(cmd(['runuser','-u','postgres','--','psql','-XAtq','-d','forgejo','-c', "SELECT count(*) FROM access_token WHERE name LIKE 'forgejo-sso-probe-%' OR name LIKE 'declarative-rename-%';"]))
r['oldBootstrapCredentialExists']=secret.exists()
print(json.dumps(r,sort_keys=True))
