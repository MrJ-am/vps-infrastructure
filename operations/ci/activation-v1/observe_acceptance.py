"""Read only fixed acceptance run metadata and CI service resource counters."""
import http.client,json,subprocess
from pathlib import Path
t=Path('/var/lib/mrjam-ci-credentials/forgejo-registration-token').read_text().strip()
result={'schema_version':1,'runs':[]}
for suffix in ['/actions/runs/1','/actions/runs/1/jobs']:
 c=http.client.HTTPConnection('127.0.0.1',3004,timeout=5);c.request('GET','/api/v1/repos/MrJ-am/mrjam-validation'+suffix,headers={'Authorization':'token '+t});r=c.getresponse();raw=r.read(131073);assert len(raw)<=131072 and r.status==200;v=json.loads(raw);c.close()
 keys=('id','status','conclusion','head_sha','run_number','started_at','completed_at')
 rows=v if isinstance(v,list) else [v]
 result['runs'].append({'endpoint':suffix,'rows':[{k:j[k] for k in keys if k in j} for j in rows]})
S='/nix/store/0xiinbh7pbj479i5v28mqnjrvhvbdibf-systemd-260.2/bin/systemctl'
p=subprocess.run([S,'list-units','--all','--plain','--no-legend','mrjam-validation*'],capture_output=True,timeout=10)
names=[l.split()[0] for l in p.stdout.decode().splitlines() if l.startswith('mrjam-validation')]
result['services']=[]
for name in names:
 p=subprocess.run([S,'show',name,'-p','ActiveState','-p','Result','-p','MemoryCurrent','-p','CPUUsageNSec','-p','ExecMainStatus'],capture_output=True,timeout=10)
 result['services'].append({'unit':name,**dict(l.split('=',1) for l in p.stdout.decode().splitlines() if '=' in l)})
print(json.dumps(result,sort_keys=True))
