"""Finish exact known inputs; generated documentation must match the old hashes."""
from pathlib import Path
import hashlib,json,os,shutil,subprocess
ROOT=Path(__file__).resolve().parents[3]
LOCAL=ROOT/'.local/ci-artifact-recovery-20261102'
ELM=Path('/nix/store/y18rr9k4yw3qyrd2ca0p4s5g565wpd92-elm-0.19.1/bin/elm')
LOCK=LOCAL/'validator-code/workflow-runner/elm-cache.lock.json'

def main():
 lock=json.loads(LOCK.read_bytes());cache=LOCAL/'elm-cache'
 missing={p for p,h in lock['files'].items() if not (cache/p).is_file() or hashlib.sha256((cache/p).read_bytes()).hexdigest()!=h}
 expected={'0.19.1/packages/elm/http/2.0.0/docs.json','0.19.1/packages/elm/time/1.0.0/docs.json'}
 assert missing<=expected
 if missing:
  private=LOCAL/'elm-doc-generation-cache';shutil.copytree(cache,private)
  for project,version in [('http','2.0.0'),('time','1.0.0')]:
   name=f'0.19.1/packages/elm/{project}/{version}/docs.json'
   if name not in missing:continue
   work=LOCAL/('elm-doc-generation-'+project);shutil.copytree(cache/Path(name).parent,work)
   env={'PATH':os.environ['PATH'],'ELM_HOME':str(private),'GHCRTS':'-N2','LANG':'C','LC_ALL':'C'}
   subprocess.run([str(ELM),'make','--docs=docs.json'],cwd=work,env=env,check=True,timeout=120,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
   raw=(work/'docs.json').read_bytes();assert hashlib.sha256(raw).hexdigest()==lock['files'][name];(cache/name).write_bytes(raw)
 assert all(hashlib.sha256((cache/p).read_bytes()).hexdigest()==h for p,h in lock['files'].items())
 source=ROOT/'.local/forgejo-source-history-20261102/vps-infrastructure.git'
 for name in ['toolchains.nix','toolchains.lock.json']:
  raw=subprocess.check_output(['git','--git-dir='+str(source),'show','3836559dd79c053d2f6a4c7aaa2b4c1add6575b6:operations/builds/'+name])
  path=LOCAL/'historical-build-support'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
 (LOCAL/'policy.json').write_bytes((LOCAL/'policy-fixture.json').read_bytes())
 print(json.dumps({'elm_cache_files_exact':len(lock['files']),'historical_compiler_recipe_materialized':True,'synthetic_policy_only':True}))
if __name__=='__main__':main()
