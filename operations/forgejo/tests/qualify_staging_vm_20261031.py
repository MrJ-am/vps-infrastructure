import json,subprocess,time
from pathlib import Path
root=Path('/workspace/shared/mrjam-declarative-nix')
name='staging-systemd-20261031-02'
command=['nix','build','--offline','--no-link','--json','--file','/workspace/mrjam-validation/operational-review/staging-sources-systemd.nix','--arg','nixpkgs','/nix/store/ydk30pf7qngrw0ws113m9p005p681rxy-source']
start=time.monotonic()
with (root/(name+'.json')).open('x') as stdout,(root/(name+'.log')).open('x') as stderr:
    result=subprocess.run(command,stdout=stdout,stderr=stderr)
record={'command':command,'exit_code':result.returncode,'wall_seconds':round(time.monotonic()-start,3),'production_access':False}
(root/(name+'-execution.json')).write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record),flush=True)
raise SystemExit(result.returncode)
