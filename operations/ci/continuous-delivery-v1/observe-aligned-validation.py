"""Read only fixed acceptance run metadata and CI service resource counters."""
import http.client,json,subprocess
from pathlib import Path
t=Path('/var/lib/mrjam-ci-credentials/forgejo-registration-token').read_text().strip()
result={'schema_version':1,'runs':[]}
for suffix in ['/actions/runs/2','/actions/runs/2/jobs']:
 c=http.client.HTTPConnection('127.0.0.1',3004,timeout=5);c.request('GET','/api/v1/repos/MrJ-am/mrjam-validation'+suffix,headers={'Authorization':'token '+t});r=c.getresponse();raw=r.read(131073);assert len(raw)<=131072 and r.status==200;v=json.loads(raw);c.close()
 keys=('id','status','conclusion','head_sha','run_number','started_at','completed_at','created_at','updated_at','run_started_at')
 rows=v if isinstance(v,list) else [v]
 result['runs'].append({'endpoint':suffix,'rows':[{k:j[k] for k in keys if k in j} for j in rows]})
S='/nix/store/0xiinbh7pbj479i5v28mqnjrvhvbdibf-systemd-260.2/bin/systemctl'
p=subprocess.run([S,'list-units','--all','--plain','--no-legend','mrjam-validation*'],capture_output=True,timeout=10)
names=[l.split()[0] for l in p.stdout.decode().splitlines() if l.startswith('mrjam-validation')]
result['services']=[]
for name in names:
 p=subprocess.run([S,'show',name,'-p','ActiveState','-p','Result','-p','MemoryCurrent','-p','CPUUsageNSec','-p','ExecMainStatus'],capture_output=True,timeout=10)
 result['services'].append({'unit':name,**dict(l.split('=',1) for l in p.stdout.decode().splitlines() if '=' in l)})
result['worker_process_kinds']={}
result['rust_release_compilation']=False
for name in names:
 if not name.startswith('mrjam-validation-worker@'):continue
 p=subprocess.run([S,'show',name,'-p','ControlGroup','--value'],capture_output=True,timeout=5)
 group=p.stdout.decode().strip()
 if not group.startswith('/') or '..' in group:continue
 for f in (Path('/sys/fs/cgroup')/group.lstrip('/')).rglob('cgroup.procs'):
  for pid in f.read_text().splitlines():
   try:comm=Path('/proc',pid,'comm').read_text().strip()
   except FileNotFoundError:continue
   if comm=='cargo':
    try:result['rust_release_compilation'] |= b'--release' in Path('/proc',pid,'cmdline').read_bytes().split(b'\0')
    except FileNotFoundError:pass
   if comm in ('rustc','cargo','node','elm','python3','nix','cc','ld','bwrap'):
    result['worker_process_kinds'][comm]=result['worker_process_kinds'].get(comm,0)+1
print(json.dumps(result,sort_keys=True))
