#!/usr/bin/env python3
"""Replace only two inactive, exact runtime unit links; no service activation."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import stat
import subprocess
import sys

BINDING = None  # Sealed separately after qualification of both replacements.
PREVIOUS = '/nix/store/jn9rf2fgk2y6dbhdnjwkmfww3pchkyb9-nixos-system-nixos-26.05.8639.c5c4a43b0e80'
UNITS = frozenset(('mrjam-kanidm-passkey-portal.service','mrjam-kanidm-worker-provision.service'))
RUNTIME = Path('/run/systemd/system')
STORE = r'/nix/store/[0-9a-df-np-sv-z]{32}-[A-Za-z0-9+._?=-]+'


class Refused(Exception):
    pass


def require(value):
    if not value:
        raise Refused()


def validate(binding):
    require(type(binding) is dict and set(binding) == UNITS)
    for unit, versions in binding.items():
        require(type(versions) is dict and set(versions) == {'previous','next'})
        require(versions['previous'] != versions['next'])
        for item in versions.values():
            require(type(item) is dict and set(item) == {'path','sha256'})
            require(type(item['path']) is str and re.fullmatch(STORE+'/'+re.escape(unit),item['path']))
            require(type(item['sha256']) is str and re.fullmatch(r'[a-f0-9]{64}',item['sha256']))
            require(os.path.realpath(item['path']) == item['path'])
            fd = os.open(item['path'],os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
            with os.fdopen(fd,'rb') as stream:
                info = os.fstat(stream.fileno())
                require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o222
                        and 0 < info.st_size <= 65536)
                data = stream.read(65537)
            require(len(data) == info.st_size and hashlib.sha256(data).hexdigest() == item['sha256'])
    return binding


def runtime_directory():
    fd = os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        for part in RUNTIME.parts[1:]:
            child = os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=fd)
            os.close(fd)
            fd = child
            info = os.fstat(fd)
            require(info.st_uid == 0 and not info.st_mode & 0o022)
        return fd
    except BaseException:
        os.close(fd)
        raise


def manager(action,unit=None):
    require(action == 'show' and unit in UNITS or action == 'daemon-reload' and unit is None)
    args = [PREVIOUS+'/sw/bin/systemctl',action]
    if action == 'show':
        args += [unit,'--no-pager','--property=LoadState,ActiveState,FragmentPath,DropInPaths']
    result = subprocess.run(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL,timeout=30,check=False,
                            env={'LANG':'C','LC_ALL':'C'})
    require(result.returncode == 0 and len(result.stdout) <= 8192)
    return result.stdout


def inactive(unit,paths):
    fields = {}
    for line in manager('show',unit).decode('ascii').splitlines():
        name,value = line.split('=',1)
        require(name not in fields)
        fields[name] = value
    require(set(fields) == {'LoadState','ActiveState','FragmentPath','DropInPaths'})
    require(fields['LoadState'] == 'loaded' and fields['ActiveState'] in ('inactive','failed'))
    require(fields['DropInPaths'] == '' and os.path.realpath(fields['FragmentPath']) in paths)


def replace_links(fd,binding):
    # Validate both existing targets before the first replacement. A retry can
    # complete an interruption after either exact link was already replaced.
    observed = {}
    for unit in sorted(UNITS):
        info = os.stat(unit,dir_fd=fd,follow_symlinks=False)
        require(stat.S_ISLNK(info.st_mode) and info.st_uid == 0)
        target = os.readlink(unit,dir_fd=fd)
        require(target in {item['path'] for item in binding[unit].values()})
        observed[unit] = target
    for unit in sorted(UNITS):
        target = binding[unit]['next']['path']
        if observed[unit] == target:
            continue
        temporary = '.'+unit+'.mrjam-upgrade'
        try:
            os.symlink(target,temporary,dir_fd=fd)
        except FileExistsError:
            info = os.stat(temporary,dir_fd=fd,follow_symlinks=False)
            require(stat.S_ISLNK(info.st_mode) and info.st_uid == 0 and os.readlink(temporary,dir_fd=fd) == target)
        require(os.readlink(unit,dir_fd=fd) == observed[unit])
        os.replace(temporary,unit,src_dir_fd=fd,dst_dir_fd=fd)
        os.fsync(fd)


def upgrade(binding):
    require(os.geteuid() == 0 and os.path.realpath('/run/current-system') == PREVIOUS)
    binding = validate(binding)
    fd = runtime_directory()
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        for unit in sorted(UNITS):
            inactive(unit,{item['path'] for item in binding[unit].values()})
        replace_links(fd,binding)
        manager('daemon-reload')
        for unit in sorted(UNITS):
            inactive(unit,{binding[unit]['next']['path']})
    finally:
        os.close(fd)
    return {'schema_version':1,'code':'PASSKEY_INACTIVE_UNITS_UPDATED','services_started':False,
            'credential_creation':False,'application_generation_changed':False}


def main():
    if len(sys.argv) != 1:
        return 64
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    os.umask(0o077)
    try:
        result = upgrade(BINDING)
    except Exception:
        print('{"schema_version":1,"code":"PASSKEY_UNIT_UPGRADE_REFUSED"}')
        return 1
    print(json.dumps(result,sort_keys=True,separators=(',',':')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
