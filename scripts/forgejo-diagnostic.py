#!/usr/bin/env python3
"""Read-only, allowlisted system metadata for the Forgejo integration."""
import json, pathlib, subprocess, hashlib

def cmd(args, timeout=180):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=timeout).stdout.strip()

NIXPKGS='/nix/store/81s59zcy998ym4b36ayr29cjc9yhma5n-nixos-26.05.8639.c5c4a43b0e80/nixos'
EXPR='''let e=import <nixpkgs/nixos/lib/eval-config.nix> {system="x86_64-linux";modules=[/etc/nixos/configuration.nix];}; c=e.config; in {
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
   'forgejo_paths_present':{p:pathlib.Path(p).exists() for p in ('/var/lib/forgejo','/var/backup/forgejo')}}
print(json.dumps(r,sort_keys=True))
