from pathlib import Path
import subprocess,sys,json,importlib.util,hashlib,os
R=Path.cwd();L=R/'.local/ci-artifact-recovery-20261102';V=L/'validation-code';G=R/'.local/deployment-20261101/private-histories-20261102/bare';PUB=R/'.local/forgejo-source-history-20261102';REV='eb71ffe5944943474c5ee483e66c270b5976ab90'
def git(repo,*a):return subprocess.check_output(['git','-c','core.hooksPath=/dev/null','--git-dir='+str(repo),*a],stderr=subprocess.DEVNULL)
def put(p,raw):p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
def sha(b):return hashlib.sha256(b).hexdigest()
sys.path.insert(0,str(V/'workflow-runner'));spec=importlib.util.spec_from_file_location('prepare_input',V/'workflow-runner/prepare_input.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
observations=json.loads((V/'workflow-runner/source-observations.json').read_text())
static=L/'static-code-export';static.mkdir()
for source in observations['sources']:
 repo=PUB/(source['repository'].split('/')[1]+'.git')
 tree_name=source['complete_tree_file'];raw=git(G/'mrjam-validation.git','show',REV+':workflow-runner/'+tree_name)
 assert sha(raw)==source['complete_tree_sha256'];put(V/'workflow-runner'/tree_name,raw)
 for item in source['selected_files']:
  name=item['path'];assert not name.startswith('/') and '..' not in Path(name).parts and not name.endswith('.gz')
  raw=git(repo,'show',source['revision']+':'+name)
  assert len(raw)==item['bytes'] and sha(raw)==item['sha256'] and m.gate.git_blob(raw)==item['git_blob']
  put(static/'sources'/source['id']/name,raw)
root=L/'proposal-base';root.mkdir(mode=0o700)
sources=m.materialize_static(root,static)
inventory=json.loads((L/'selected-inputs-inventory.json').read_text());baseline=json.loads((R/'operations/builds/sources.lock.json').read_text())
# Only already-inspected exact code selections; no older tree checkout, dumps or archives.
for identifier in ('vision','mateval','infrastructure','platform'):
 item=inventory[identifier];sources.append(m.materialize_git(root,Path(item['repository']),identifier,item['revision'],baseline))
value={'schema_version':1,'status':'proposed-not-independently-adopted','rules_revision':REV,'sources':sources,'frontends':m.frontend_policy(root,sources),'out_of_scope':['etp-vise: source inventory and qualification remain outside the migrated VPS scope']}
value['rust_manifests']={}
for name in sorted(m.policy.MANIFESTS):
 parts=Path(name).parts;source,path=(parts[1],str(Path(*parts[2:]))) if parts[0]=='components' else ('platform',name)
 value['rust_manifests'][name]=m.policy.sha(root/'sources'/source/path)
m.policy.checked_policy(value)
put(L/'policy-base.json',(json.dumps(value,sort_keys=True,indent=2)+'\n').encode())
files=[{'path':str(p.relative_to(root)),'bytes':p.stat().st_size,'sha256':m.policy.sha(p)} for p in sorted(root.rglob('*')) if p.is_file()]
manifest={'schema_version':1,'rules_revision':REV,'files':files}
raw=(json.dumps(manifest,sort_keys=True,separators=(',',':'))+'\n').encode();put(root/'manifest.json',raw)
print(json.dumps({'files':len(files),'manifest_sha256':sha(raw),'expected_manifest_equal':sha(raw)=='8bf05fb9065a4c91e565ec0d37f24f2c556f315109823ccdef95c6354b423d6a','policy_sha256':sha((L/'policy-base.json').read_bytes())}))
