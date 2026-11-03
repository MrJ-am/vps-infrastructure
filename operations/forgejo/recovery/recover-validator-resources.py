from pathlib import Path
import json,subprocess,hashlib,urllib.request,tarfile,io
R=Path.cwd();L=R/'.local/ci-artifact-recovery-20261102';out=L/'frontend-resources';g=R/'.local/deployment-20261101/private-histories-20261102/bare/Signature.git';lock=json.loads((R/'operations/builds/frontend-resources-operationnel-20261030.lock.json').read_text());archives={}
for e in lock['files']:
 p=e['provenance'];name=e['source_path']
 if name.startswith('signature/'):
  b=subprocess.check_output(['git','--git-dir='+str(g),'cat-file','blob',p['git_blob']]);assert subprocess.check_output(['git','--git-dir='+str(g),'rev-parse',p['revision']+':'+p['path']],text=True).strip()==p['git_blob']
 else:
  assert name.startswith('katex-dist/')
  if p['url'] not in archives:
   with urllib.request.urlopen(p['url'],timeout=45) as r:raw=r.read(20*1024*1024)
   assert hashlib.sha256(raw).hexdigest()==p['archive_sha256'];archives[p['url']]=tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz')
  t=archives[p['url']];m=t.getmember('package/dist/'+name.removeprefix('katex-dist/'));assert m.isfile();b=t.extractfile(m).read()
 assert hashlib.sha256(b).hexdigest()==e['sha256'];f=out/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(b);f.chmod(0o644)
print(json.dumps({'resource_files':len(lock['files']),'all_content_hashes_exact':True}))
