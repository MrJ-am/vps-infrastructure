from pathlib import Path
import subprocess,sys,json,importlib.util,hashlib
R=Path.cwd();L=R/'.local/ci-artifact-recovery-20261102';V=L/'validation-code';G=R/'.local/deployment-20261101/private-histories-20261102/bare';PUB=R/'.local/forgejo-source-history-20261102';REV='eb71ffe5944943474c5ee483e66c270b5976ab90'
def git(repo,*a):return subprocess.check_output(['git','-c','core.hooksPath=/dev/null','--git-dir='+str(repo),*a],stderr=subprocess.DEVNULL)
selected=['check_git_tree.py','workflow-runner/prepare_input.py','workflow-runner/policy.py','workflow-runner/sandbox.py','workflow-runner/source-observations.json','workflow-runner/frontend-policy-20261031.json']
for name in selected:
 p=V/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(git(G/'mrjam-validation.git','show',REV+':'+name))
sys.path.insert(0,str(V/'workflow-runner'));spec=importlib.util.spec_from_file_location('prepare_input',V/'workflow-runner/prepare_input.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
front=json.loads((V/'workflow-runner/frontend-policy-20261031.json').read_text());base=json.loads((R/'operations/builds/sources.lock.json').read_text())
repos={'vision':G/'vision.git','mateval':G/'matheval.git','infrastructure':PUB/'vps-infrastructure.git','platform':G/'mrjam-plateforme.git'}
versions={x['id']:x['revision'] for x in front['sources']};versions.update({x['id']:x['revision'] for x in json.loads((R/'operations/forgejo/qualification-complete-chain-20261031.json').read_text())['result']['integration_evidence']['verification']['sources']})
result={}
for identifier,repo in repos.items():
 entries=git(repo,'ls-tree','-r','-z',versions[identifier]).split(b'\0');chosen=[]
 for entry in entries:
  if not entry:continue
  fields,name=entry.split(b'\t',1);mode,kind,blob=fields.decode().split();name=name.decode()
  if kind=='blob' and m.selected(identifier,name,base):chosen.append({'path':name,'mode':mode,'blob':blob})
 result[identifier]={'repository':str(repo),'revision':versions[identifier],'selected':chosen}
 print(identifier,len(chosen),'sql paths',[x['path'] for x in chosen if x['path'].endswith('.sql')])
(L/'selected-inputs-inventory.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
