#!/usr/bin/env python3
"""Read-only preconditions for the independent ViSe service; never print secrets."""
import json, subprocess, pathlib, socket

def run(args):
 p=subprocess.run(args,text=True,capture_output=True)
 return {'ok':p.returncode==0,'output':p.stdout.strip()[:2000]}
report={
 'domain':'vise.mrj.am',
 'generation':str(pathlib.Path('/run/current-system').resolve()),
 'configuration':str(pathlib.Path('/etc/nixos/configuration.nix').resolve()),
 'services':{s:run(['systemctl','is-active',s]) for s in ['nginx','postgresql','docker','mrjam-metier','kanidm','nextcloud-phpfpm','forgejo']},
 'postgres':run(['runuser','-u','postgres','--','psql','-XAtq','-h','/run/postgresql','-d','postgres','-c',"SELECT json_build_object('version',current_setting('server_version'),'listen',current_setting('listen_addresses'),'port',current_setting('port'),'etpDatabaseExists',EXISTS(SELECT FROM pg_database WHERE datname='etp_carnet'),'etpRoleExists',EXISTS(SELECT FROM pg_roles WHERE rolname='etp_carnet'))"]),
 'etpUser':run(['getent','passwd','etp_carnet']),
 'uid10001':run(['getent','passwd','10001']),
 'disk':run(['df','-h','/var/lib']),
 'listeners':run(['ss','-lnt']),
}
print(json.dumps(report,indent=2))
