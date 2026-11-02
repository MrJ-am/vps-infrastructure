#!/usr/bin/env python3
"""Only Nix metadata for the exact previous system closure, never file contents."""
import base64
import json
import os
import re
import resource
import subprocess
import sys

PREVIOUS = "/nix/store/jn9rf2fgk2y6dbhdnjwkmfww3pchkyb9-nixos-system-nixos-26.05.8639.c5c4a43b0e80"
PREVIOUS_NAR = "sha256-ety23BZuKSrZ3Gfltw4q3Fa4hZSkMviYv6GclodXkOk="
STORE = re.compile(r"/nix/store/[0-9a-df-np-sv-z]{32}-[A-Za-z0-9+._?=-]+\Z")


def require(value):
    if not value:
        raise ValueError()


def parse(raw):
    require(type(raw) is bytes and 0 < len(raw) <= 8*1024*1024)
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result)
            result[key] = value
        return result
    values = json.loads(raw, object_pairs_hook=unique,
                        parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    if type(values) is dict:
        values = [dict(item, path=path) for path, item in values.items()]
    require(type(values) is list and 1 <= len(values) <= 4096)
    result = {}
    size = 0
    for item in values:
        require(type(item) is dict)
        path, digest, count = item.get('path'), item.get('narHash'), item.get('narSize')
        require(type(path) is str and STORE.fullmatch(path) and path not in result)
        require(type(digest) is str and re.fullmatch(r'sha256-[A-Za-z0-9+/]{43}=', digest))
        decoded = base64.b64decode(digest[7:], validate=True)
        require(len(decoded) == 32 and base64.b64encode(decoded).decode() == digest[7:])
        require(type(count) is int and 0 < count <= 64*1024**3)
        result[path] = digest
        size += count
    require(result.get(PREVIOUS) == PREVIOUS_NAR and size <= 128*1024**3)
    return {'generation': PREVIOUS, 'artifacts': result, 'nar_bytes': size}


def main():
    if len(sys.argv) != 1 or os.geteuid() != 0:
        return 64
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    try:
        require(os.path.realpath('/run/current-system') == PREVIOUS)
        result = subprocess.run([PREVIOUS+'/sw/bin/nix', '--extra-experimental-features', 'nix-command',
                                 'path-info', '--json', '--recursive', PREVIOUS],
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                timeout=60, check=False, env={'LANG':'C','LC_ALL':'C','NIX_PATH':''})
        require(result.returncode == 0)
        value = {'schema_version':1, 'code':'PREVIOUS_CLOSURE_OBSERVED', **parse(result.stdout),
                 'application_content_read':False, 'production_mutation':False}
    except Exception:
        print('{"schema_version":1,"code":"PREVIOUS_CLOSURE_UNAVAILABLE"}')
        return 1
    print(json.dumps(value,sort_keys=True,separators=(',',':')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
