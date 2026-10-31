import json,subprocess,time
from pathlib import Path
out=Path('/workspace/shared/mrjam-declarative-nix')
for name, command in [('staging-module-20261031-01',['nix-instantiate','--eval','--strict','--json','operations/forgejo/tests/staging-module-evaluation.nix','--arg','nixpkgs','/nix/store/ydk30pf7qngrw0ws113m9p005p681rxy-source']),('staging-build-20261031-01',['nix','build','--offline','--no-link','--json','--file','/workspace/shared/mrjam-declarative-build/staging-package-20261031-01.nix'])]:
    start=time.monotonic()
    with (out/(name+'.json')).open('x') as stdout,(out/(name+'.log')).open('x') as stderr:
        r=subprocess.run(command,stdout=stdout,stderr=stderr)
    record={'command':command,'exit_code':r.returncode,'wall_seconds':round(time.monotonic()-start,3)}
    (out/(name+'-execution.json')).write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record),flush=True)
    if r.returncode: raise SystemExit(r.returncode)
