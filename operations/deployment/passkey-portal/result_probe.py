#!/usr/bin/env python3
"""Closed post-provision observation: three fixed files and three GET /v1/self."""
import fcntl
import json
import os
from pathlib import Path
import re
import resource
import runpy
import signal
import stat
import sys

ROOT = Path(__file__).resolve().parent
STATE = Path('/var/lib/mrjam-identite')
ROLES = ('admission','cycle','replay')


def read_tokens(provision, path=STATE):
    H = provision['H']
    require = provision['require']
    descriptor = H['open_directory'](path)
    lock = None
    try:
        meta = os.fstat(descriptor)
        require(meta.st_uid == 0 and meta.st_gid == 0 and stat.S_IMODE(meta.st_mode) == 0o700)
        # Do not create a lock or any other file. An active provisioning run
        # must finish before the final observation can be returned.
        try:
            lock = os.open('.worker-provision.lock', os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=descriptor)
        except FileNotFoundError:
            pass
        else:
            meta = os.fstat(lock)
            require(stat.S_ISREG(meta.st_mode) and meta.st_uid == meta.st_gid == 0
                    and meta.st_nlink == 1 and stat.S_IMODE(meta.st_mode) == 0o600)
            fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
        tokens = {}
        for role in ROLES:
            name = 'kanidm-' + role + '.token'
            try:
                meta = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                require(meta.st_gid == 0)
                raw = H['read_file'](descriptor, name, 4096)
            except FileNotFoundError:
                tokens[role] = None
                continue
            token = raw.decode('ascii').removesuffix('\n')
            require(provision['TOKEN'].fullmatch(token))
            tokens[role] = token
        return tokens
    finally:
        if lock is not None:
            os.close(lock)
        os.close(descriptor)


def examine(provision, tokens, get):
    result = {'schema_version':1, 'read_only':True, 'all_tokens_present':False,
              'tokens_distinct':False, 'all_expected_memberships':False,
              'write_authorization_proved':False}
    for role in ROLES:
        token = tokens.get(role)
        state = {'present':token is not None,'authenticated_service':False,'expected_memberships':False}
        if token is not None:
            value = get(token)
            observed = provision['P']['identity'](value, provision['SERVICES'][role])
            state['authenticated_service'] = observed is not None
            try:
                provision['token_identity'](lambda credential, method, path: value, token, role)
            except Exception:
                pass
            else:
                state['expected_memberships'] = True
        result[role] = state
    result['all_tokens_present'] = all(result[role]['present'] for role in ROLES)
    result['tokens_distinct'] = result['all_tokens_present'] and len(set(tokens.values())) == 3
    result['all_expected_memberships'] = all(result[role]['expected_memberships'] for role in ROLES)
    return result


def main():
    try:
        resource.setrlimit(resource.RLIMIT_CORE,(0,0))
        def timeout(*_):
            raise RuntimeError()
        signal.signal(signal.SIGALRM, timeout)
        signal.alarm(25)
        if len(sys.argv) != 1 or os.geteuid() != 0:
            raise RuntimeError()
        public = json.loads((ROOT/'result-public.json').read_bytes())
        if set(public) != {'provision_module'} or not re.fullmatch(r'/nix/store/[a-z0-9]{32}-mrjam-kanidm-worker-provision-2/libexec/provision.py', public['provision_module']):
            raise RuntimeError()
        provision = runpy.run_path(public['provision_module'],run_name='read_only_provision_helpers')
        base = Path(public['provision_module']).parent
        trust = provision['H']['strict_json']((base/'probe-public.json').read_bytes())
        context = provision['P']['tls_context']((base/'ca.pem').read_bytes(),trust['ca_sha256'])
        result = examine(provision, read_tokens(provision),
            lambda token: provision['P']['request'](token,'/v1/self',context))
        print(json.dumps(result,sort_keys=True,separators=(',',':')))
        return 0
    except Exception:
        print('{"error":"WORKER_RESULT_PROBE_REFUSED"}',file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
