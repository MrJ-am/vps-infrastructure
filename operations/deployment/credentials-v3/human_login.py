#!/usr/bin/env python3
"""Human-only terminal entry. Official CLI handles password/passkey interaction."""
import os
from pathlib import Path
import re
import resource
import runpy
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
P = runpy.run_path(str(ROOT/'provision.py'),run_name='human_helpers')
DIRECTORY = Path('/run/mrjam-kanidm-worker-login')


def main():
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    os.umask(0o077)
    if len(sys.argv) != 1 or os.geteuid() != 0 or not all(os.isatty(n) for n in (0,1,2)):
        print('HUMAN_TERMINAL_REQUIRED',file=sys.stderr)
        return 1
    # Program paths are generated in the immutable Nix package.
    public = P['H']['strict_json']((ROOT/'human-public.json').read_bytes())
    if set(public) != {'kanidm','systemctl'} or not all(isinstance(v,str) and v.startswith('/nix/store/') for v in public.values()):
        return 1
    try:
        DIRECTORY.mkdir(mode=0o700)
    except FileExistsError:
        print('TEMPORARY_LOGIN_ALREADY_PRESENT',file=sys.stderr)
        return 1
    environments = {'PATH':str(Path(public['kanidm']).parent),'TERM':os.environ.get('TERM','xterm'),
                    'LANG':'C.UTF-8'}
    sessions = []
    status = 1
    def command(cache,name,verb):
        return [public['kanidm'],verb,'-H','https://log.mrj.am','-C',str(ROOT/'ca.pem'),
                '--token-cache-path',str(cache),'-D',name]
    def authenticate(cache,name):
        subprocess.run(command(cache,name,'login'),env=environments,check=True)
        fd = P['H']['open_directory'](DIRECTORY)
        try:
            raw = P['H']['read_file'](fd,cache.name,65536)
            reauth = P['needs_reauth'](raw)
        finally:
            os.close(fd)
        if reauth:
            subprocess.run(command(cache,name,'reauth'),env=environments,check=True)
    try:
        print('Le client Kanidm vous authentifie personnellement. Ne communiquez aucun secret à l’agent.')
        name = input('Compte autorisé à gérer les comptes de service et les personnes : ').strip()
        if not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}',name):
            return 1
        identity = DIRECTORY/'identity.json'
        sessions.append((identity,name))
        authenticate(identity,name)
        access_name = input('Compte autorisé à gérer les accès (Entrée = même compte) : ').strip() or name
        if not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}',access_name):
            return 1
        access = DIRECTORY/'access.json'
        if access_name == name:
            # This cache is purpose-built by the commands above; no existing
            # personal CLI or browser cache is read or copied.
            fd = P['H']['open_directory'](DIRECTORY)
            try:
                raw = P['H']['read_file'](fd,'identity.json',65536)
                P['cache_token'](raw)
                out = os.open('access.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=fd)
                try:
                    if os.write(out,raw) != len(raw):
                        return 1
                    os.fsync(out)
                finally:
                    os.close(out)
            finally:
                os.close(fd)
        else:
            sessions.append((access,access_name))
            authenticate(access,access_name)
        # No token/password is placed in argv or environment. LoadCredential
        # gives these two dedicated temporary caches to the reviewed unit.
        subprocess.run([public['systemctl'],'start','mrjam-kanidm-worker-provision.service'],
                       env={'PATH':str(Path(public['systemctl']).parent)},check=True)
        print('WORKER_CREDENTIALS_PREPARED')
        status = 0
    except (Exception,KeyboardInterrupt):
        print('WORKER_PROVISION_NOT_COMPLETED',file=sys.stderr)
    finally:
        # Revoke only sessions from this dedicated login, including an aborted
        # authentication after the official CLI has persisted its cache.
        for cache,name in sessions:
            if cache.exists():
                subprocess.run(command(cache,name,'logout'),env=environments,
                               stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
        shutil.rmtree(DIRECTORY)
    return status


if __name__ == '__main__':
    raise SystemExit(main())
