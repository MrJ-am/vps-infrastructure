#!/usr/bin/env python3
"""Only the immutable current generation's NAR metadata, no state content."""
import base64
import json
import os
import re
import subprocess
import sys

PREVIOUS="/nix/store/jn9rf2fgk2y6dbhdnjwkmfww3pchkyb9-nixos-system-nixos-26.05.8639.c5c4a43b0e80"


def parse(raw):
    if not isinstance(raw,bytes) or len(raw)>65536:
        raise ValueError()
    data=json.loads(raw)
    if isinstance(data,dict) and set(data)=={PREVIOUS}:
        data=[dict(data[PREVIOUS],path=PREVIOUS)]
    if not isinstance(data,list) or len(data)!=1 or not isinstance(data[0],dict):
        raise ValueError()
    item=data[0]
    if item.get('path')!=PREVIOUS or type(item.get('narSize')) is not int or item['narSize']<=0:
        raise ValueError()
    value=item.get('narHash')
    if not isinstance(value,str) or not re.fullmatch(r'sha256-[A-Za-z0-9+/]{43}=',value):
        raise ValueError()
    if len(base64.b64decode(value[7:],validate=True))!=32:
        raise ValueError()
    return {'generation':PREVIOUS,'nar_hash':value,'nar_bytes':item['narSize']}


def main():
    if len(sys.argv)!=1 or os.geteuid()!=0:
        return 64
    try:
        if os.path.realpath('/run/current-system')!=PREVIOUS:
            raise ValueError()
        result=subprocess.run([PREVIOUS+'/sw/bin/nix','--extra-experimental-features','nix-command',
                               'path-info','--json',PREVIOUS],stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=20,check=False,
                              env={'LANG':'C','LC_ALL':'C','NIX_PATH':''})
        if result.returncode!=0:
            raise ValueError()
        value={'schema_version':1,'code':'GENERATION_NAR_OBSERVED',**parse(result.stdout),
               'application_content_read':False,'production_mutation':False}
    except Exception:
        print('{"schema_version":1,"code":"GENERATION_NAR_UNAVAILABLE"}')
        return 1
    print(json.dumps(value,sort_keys=True,separators=(',',':')))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
