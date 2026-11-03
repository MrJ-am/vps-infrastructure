"""Dispatch the adopted validation workflow once, with an exact source digest."""
import os,json,fcntl,hashlib,base64,importlib.util,signal
from pathlib import Path
REG='/nix/store/y7shwh8rnvpsri88shhflp7av0l5hx4l-mrjam-forgejo-registration/register_runner.py'
BOOT='/nix/store/8pkxq7pahlmhlmf6v890q2ica69cflsy-mrjam-forgejo-technical-bootstrap-1/libexec/core.py'
DIGEST='8177667ea392aacd4c31ae32c03f2e75fd11b15bd716567ad6b412a9cd60defb'
STATE=Path('/var/lib/mrjam-ci-credentials/acceptance-dispatch-001.json')
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
R=load('registration',REG)
WORKFLOW=R.BASE+'/contents/.forgejo/workflows/independent-validation.yml?ref=main'
RUNS=R.BASE+'/actions/runs'
DISPATCH=R.BASE+'/actions/workflows/independent-validation.yml/dispatches'
class Transport(R.Transport):
 def endpoint_allowed(self,method,path):
  return super().endpoint_allowed(method,path) or (method=='GET' and path in (WORKFLOW,RUNS)) or (method=='POST' and path==DISPATCH)
def main():
 signal.alarm(150);os.umask(0o077)
 R.api.require(os.geteuid()==0 and os.uname().nodename=='srv1982677','HOST_REFUSED')
 lock=os.open('/var/lib/mrjam-cutover/first-deployment/transaction.lock',os.O_RDWR|os.O_NOFOLLOW);fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 R.api.require(not STATE.exists(),'DISPATCH_ALREADY_ATTEMPTED')
 policy=R.api.document(R.POLICY)
 token=Path('/var/lib/mrjam-ci-credentials/forgejo-registration-token').read_text().strip()
 t=Transport(token);R.prerequisites(t,policy)
 wf=t.request('GET',WORKFLOW)
 R.api.require(wf.get('encoding')=='base64' and hashlib.sha256(base64.b64decode(wf['content'])).hexdigest()=='cd01f21d4df118d1c52d9e76ab600e6bebbd746415c4f57cc744c8d5f6f2b5de','WORKFLOW_REFUSED')
 runs=t.request('GET',RUNS)
 R.api.require(runs.get('total_count')==0 and runs.get('workflow_runs')==[],'EXISTING_RUNS_REQUIRE_INSPECTION')
 B=load('bootstrap',BOOT)
 with B.governance_lease() as owner:
  runners=R.Transport(owner).request('GET',R.RUNNERS)
  identity_path=Path(R.STATE+'/registration/identity.json');info=identity_path.lstat()
  R.api.require(info.st_uid==949 and info.st_nlink==1 and (info.st_mode & 0o777)==0o400,'IDENTITY_FILE_REFUSED')
  expected=R.identity(json.loads(identity_path.read_bytes()))
  R.api.require(len(runners)==1,'RUNNER_COUNT_REFUSED');R.verify_remote(runners[0],expected)
  R.api.require(runners[0].get('status')=='idle' and runners[0].get('labels')==['mrjam-controller'],'RUNNER_NOT_READY')
 fd=os.open(STATE,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 os.write(fd,json.dumps({'phase':'dispatching','proposal_digest':DIGEST,'rules_revision':policy['rules_revision']}).encode());os.fsync(fd);os.close(fd)
 result=t.request('POST',DISPATCH,{'ref':'main','inputs':{'proposal_digest':DIGEST},'return_run_info':True})
 R.api.require(set(result)=={'id','run_number','jobs'} and type(result['id']) is int and result['id']>0,'RUN_RESPONSE_REFUSED')
 with STATE.open('w') as f:json.dump({'phase':'dispatched',**result,'proposal_digest':DIGEST},f);f.flush();os.fsync(f.fileno())
 print(json.dumps({'code':'VALIDATION_DISPATCHED',**result,'temporary_owner_token_revoked':True},sort_keys=True))
if __name__=='__main__':
 try:main()
 except R.api.Refused as e:print(json.dumps({'code':e.code}));raise SystemExit(2)
