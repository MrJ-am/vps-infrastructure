#!/usr/bin/env python3
"""Open only the two exact temporary human-authentication units, no arguments."""
import hashlib
import fcntl
import json
import os
from pathlib import Path
import re
import resource
import stat
import subprocess
import sys
import time

BINDING = None  # Sealed separately with the two qualified immutable units.
PREVIOUS = "/nix/store/jn9rf2fgk2y6dbhdnjwkmfww3pchkyb9-nixos-system-nixos-26.05.8639.c5c4a43b0e80"
PORTAL = "mrjam-kanidm-passkey-portal.service"
ROUTE = "mrjam-passkey-nginx-route.service"
UNITS = frozenset((PORTAL, ROUTE))
RUNTIME = Path("/run/systemd/system")
SOCKET = Path("/run/mrjam-kanidm-passkey-portal/http.sock")
READY = Path("/run/mrjam-passkey-nginx-route/ready.json")
EXPECTED_READY = {"code":"PASSKEY_ROUTE_OPEN", "origin":"https://log.mrj.am",
                  "prefix":"/_mrjam-worker-provision/", "expires_after_seconds":900}
STORE = r"/nix/store/[0-9a-df-np-sv-z]{32}-[A-Za-z0-9+._?=-]+"


class Refused(Exception):
    pass


def require(value):
    if not value:
        raise Refused()


def validate(binding):
    require(type(binding) is dict and set(binding) == UNITS)
    for unit, item in binding.items():
        require(type(item) is dict and set(item) == {"path", "sha256"})
        require(type(item['path']) is str and re.fullmatch(STORE+r'/'+re.escape(unit), item['path']))
        require(type(item['sha256']) is str and re.fullmatch(r'[a-f0-9]{64}', item['sha256']))
        require(os.path.realpath(item['path']) == item['path'])
        fd = os.open(item['path'], os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        with os.fdopen(fd,'rb') as source:
            meta = os.fstat(source.fileno())
            require(stat.S_ISREG(meta.st_mode) and meta.st_uid == 0 and not meta.st_mode & 0o222
                    and 0 < meta.st_size <= 65536)
            raw = source.read(65537)
        require(len(raw) == meta.st_size and hashlib.sha256(raw).hexdigest() == item['sha256'])
    return binding


def manager(action, unit=None, capture=False):
    require(action in ('show','start','stop','daemon-reload'))
    require(unit in UNITS if action != 'daemon-reload' else unit is None)
    args = [PREVIOUS+'/sw/bin/systemctl', action]
    if unit is not None:
        args.append(unit)
    if action == 'show':
        args += ['--no-pager', '--property=LoadState,ActiveState,FragmentPath,DropInPaths']
    result = subprocess.run(args, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, timeout=300 if action=='stop' else 30,
                            check=False, env={'LANG':'C','LC_ALL':'C'})
    require(result.returncode == 0)
    if capture:
        require(len(result.stdout) <= 8192)
        return result.stdout


def observe(unit, binding, active=False):
    pairs = manager('show',unit,capture=True).decode('ascii').splitlines()
    fields = {}
    for pair in pairs:
        name, value = pair.split('=',1)
        require(name not in fields)
        fields[name] = value
    require(set(fields) == {'LoadState','ActiveState','FragmentPath','DropInPaths'})
    require(fields['DropInPaths'] == '')
    require(fields['LoadState'] in ('loaded','not-found'))
    require(fields['ActiveState'] in (('active',) if active else ('inactive','failed')))
    fragment = fields['FragmentPath']
    require((not active and fragment == '') or os.path.realpath(fragment) == binding[unit]['path'])


def directory(path):
    fd = os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        for name in path.parts[1:]:
            child = os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=fd)
            os.close(fd)
            fd = child
            meta = os.fstat(fd)
            require(meta.st_uid == 0 and not meta.st_mode & 0o022)
        return fd
    except BaseException:
        os.close(fd)
        raise


def install(binding):
    fd = directory(RUNTIME)
    try:
        # Validate every existing target before installing either link.
        absent = []
        for unit in sorted(UNITS):
            try:
                target = os.readlink(unit,dir_fd=fd)
            except FileNotFoundError:
                absent.append(unit)
            else:
                require(target == binding[unit]['path'])
        for unit in absent:
            os.symlink(binding[unit]['path'],unit,dir_fd=fd)
        os.fsync(fd)
    finally:
        os.close(fd)
    manager('daemon-reload')


def socket_ready():
    fd = directory(SOCKET.parent)
    try:
        parent = os.fstat(fd)
        meta = os.stat(SOCKET.name,dir_fd=fd,follow_symlinks=False)
        require(parent.st_gid == 60 and stat.S_IMODE(parent.st_mode) == 0o750)
        require(stat.S_ISSOCK(meta.st_mode) and meta.st_uid == 0 and meta.st_gid == 60
                and stat.S_IMODE(meta.st_mode) == 0o660)
    finally:
        os.close(fd)


def route_ready():
    folder = directory(READY.parent)
    try:
        fd = os.open(READY.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=folder)
        with os.fdopen(fd,'rb') as source:
            meta = os.fstat(source.fileno())
            require(stat.S_ISREG(meta.st_mode) and meta.st_uid == meta.st_gid == 0
                    and meta.st_nlink == 1 and stat.S_IMODE(meta.st_mode) == 0o600 and meta.st_size <= 4096)
            raw = source.read(4097)
        require(raw == (json.dumps(EXPECTED_READY,sort_keys=True,separators=(',',':'))+'\n').encode())
    finally:
        os.close(folder)


def wait_for(check, seconds):
    deadline = time.monotonic()+seconds
    while True:
        try:
            check()
            return
        except FileNotFoundError:
            require(time.monotonic() < deadline)
            time.sleep(0.2)


def open_portal_locked(binding):
    require(os.geteuid() == 0 and os.path.realpath('/run/current-system') == PREVIOUS)
    binding = validate(binding)
    for unit in sorted(UNITS):
        observe(unit,binding)
    # A completed or pending route record is not adopted by a fresh opener.
    require(not READY.exists() and not READY.is_symlink() and not SOCKET.exists() and not SOCKET.is_symlink())
    install(binding)
    started = []
    try:
        started.append(PORTAL)
        manager('start',PORTAL)
        wait_for(socket_ready,20)
        observe(PORTAL,binding,active=True)
        started.append(ROUTE)
        manager('start',ROUTE)
        wait_for(route_ready,150)
        observe(ROUTE,binding,active=True)
    except BaseException:
        # Stop the route first so its ExecStopPost restores Nginx. The portal
        # then drains any fixed provisioning task and revokes fresh sessions.
        for unit in reversed(started):
            try:
                manager('stop',unit)
            except Exception:
                pass
        raise
    return {'schema_version':1,'code':'PASSKEY_PORTAL_OPEN',
            'url':'https://log.mrj.am/_mrjam-worker-provision/', 'expires_after_seconds':900,
            'credential_creation':False,'application_generation_changed':False}


def open_portal(binding):
    fd = directory(RUNTIME)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        return open_portal_locked(binding)
    finally:
        os.close(fd)


def main():
    if len(sys.argv) != 1:
        return 64
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    os.umask(0o077)
    try:
        value = open_portal(BINDING)
    except BaseException:
        print('{"schema_version":1,"code":"PASSKEY_PORTAL_OPEN_REFUSED"}')
        return 1
    print(json.dumps(value,sort_keys=True,separators=(',',':')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
