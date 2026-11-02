#!/usr/bin/env python3
"""Build a closed stdin probe from reviewed code and the public CA only."""
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CA_HASH = '0cd98d2dd7a71afe5e2e93673933f15254c5a41a9be4682f27ec582e72c52ce0'
HELPER_NAMES = {'Refused','strict_json','open_directory','read_file'}
PROBE_NAMES = {'parse_json','tls_context','Loopback','request','identity','expired','examine'}
CONSTANTS = {'NAMES','ACCOUNTS','PATHS','TOKEN','UUID'}


def select(path, names, constants=()):
    tree = ast.parse(path.read_text())
    selected = []
    found = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names:
            selected.append(ast.unparse(node)); found.add(node.name)
        if isinstance(node, ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id in constants:
            selected.append(ast.unparse(node)); found.add(node.targets[0].id)
    if found != set(names)|set(constants):
        raise RuntimeError('STANDALONE_SOURCE_CONTRACT_CHANGED')
    return '\n\n'.join(selected)


def main():
    ca = (ROOT.parent.parent/'identity/public-ca.pem').read_bytes()
    if hashlib.sha256(ca).hexdigest() != CA_HASH:
        raise RuntimeError('PUBLIC_CA_MISMATCH')
    header = '''#!/usr/bin/env python3
"""Generated closed stdin probe. No mutation; no imports from cwd; no secret output."""
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import resource
import signal
import socket
import ssl
import stat
import sys
from datetime import datetime, timezone
'''
    main_code = '''
def standalone_tokens():
    result = {name:None for name in NAMES}
    parent = open_directory('/var/lib/mrjam-identite')
    try:
        meta = os.fstat(parent)
        if meta.st_uid != 0 or stat.S_IMODE(meta.st_mode) & 0o022:
            raise Refused()
        for name in NAMES:
            try:
                raw = read_file(parent, 'kanidm-'+name+'.token', 4096)
            except FileNotFoundError:
                continue
            value = raw.decode('ascii')
            if value.endswith('\\n'):
                value = value[:-1]
            if not TOKEN.fullmatch(value):
                raise Refused()
            result[name] = value
        return result
    finally:
        os.close(parent)

def deadline(_signal, _frame):
    raise Refused()

def main():
    previous = None
    try:
        if len(sys.argv) != 1 or os.geteuid() != 0:
            raise Refused()
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        previous = signal.signal(signal.SIGALRM, deadline)
        signal.alarm(120)
        context = tls_context(PUBLIC_CA, PUBLIC_CA_SHA256)
        result = examine(standalone_tokens(), lambda token,path: request(token,path,context), datetime.now(timezone.utc))
        print(json.dumps(result, separators=(',', ':'), sort_keys=True))
    except Exception:
        print('{"error":"KANIDM_CAPABILITY_PROBE_REFUSED"}', file=sys.stderr)
        return 1
    finally:
        if previous is not None:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous)
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
'''
    output = (header+'\n'+select(ROOT/'adapt.py',HELPER_NAMES)
              +"\n\nHELPERS = {'strict_json':strict_json}\n\n"
              +select(ROOT/'probe.py',PROBE_NAMES,CONSTANTS)
              +'\n\nPUBLIC_CA = '+repr(ca)
              +'\nPUBLIC_CA_SHA256 = '+repr(CA_HASH)+'\n'+main_code)
    compile(output, 'probe-standalone.py', 'exec')
    destination = ROOT/'probe-standalone.py'
    destination.write_text(output)
    provenance = {'schema_version':1,'sha256':hashlib.sha256(output.encode()).hexdigest(),
                  'source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
                                   for p in ('adapt.py','probe.py','generate_standalone.py')},
                  'public_ca_sha256':CA_HASH,
                  'credentials':['/var/lib/mrjam-identite/kanidm-'+name+'.token' for name in ('admission','cycle','replay')],
                  'network':'GET only, loopback127.0.0.1:8443, TLS SNI/Host log.mrj.am',
                  'alarm_seconds':120,'production_execution':False}
    (ROOT/'standalone-source.json').write_text(json.dumps(provenance,indent=2)+'\n')


if __name__ == '__main__':
    main()
