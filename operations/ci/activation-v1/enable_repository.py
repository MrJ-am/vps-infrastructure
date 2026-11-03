"""Enable Actions only on the adopted validation repository; preserve protections."""
import importlib.util,json,os,fcntl,time
from pathlib import Path

def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
B=load('bootstrap','/nix/store/8pkxq7pahlmhlmf6v890q2ica69cflsy-mrjam-forgejo-technical-bootstrap-1/libexec/core.py')
R=load('reconcile','/nix/store/brh7k2s8b8pjxkaadc4shs8sq877xni9-reconcile.py')
def main():
 os.umask(0o077)
 fd=os.open('/var/lib/mrjam-cutover/first-deployment/transaction.lock',os.O_RDWR|os.O_NOFOLLOW);fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
 try:
  policy=R.document('/etc/mrjam-forgejo/policy.json');R.validate_policy(policy)
  R.require(policy['rules_revision']=='b02bdf1b5d63dcf0e0610723788a7ca7e384932c' and policy['phase']=='operate-validation' and policy['repositories']==sorted(B.REPOSITORIES),'POLICY_REFUSED')
  with B.governance_lease() as token:
   api=R.Transport(token);snapshot=R.observe(api,policy);plan=R.plan(policy,snapshot)
   R.require(all(x['repository']=='mrjam-validation' and x['operation']=='enable-validation-actions' for x in plan['operations']),'UNEXPECTED_CHANGE')
   def consume(digest):
    path=Path('/var/lib/mrjam-ci-credentials')/('enable-actions-'+digest+'.json')
    f=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:os.write(f,R.canonical(plan));os.fsync(f)
    finally:os.close(f)
   result=R.apply(api,policy,plan,consume=consume)
  print(json.dumps({'schema_version':1,'code':'VALIDATION_REPOSITORY_ACTIONS_ENABLED','result':result,'temporary_token_revoked':True,'protections_preserved':True},sort_keys=True));return 0
 except Exception as e:
  print(json.dumps({'schema_version':1,'code':e.code if isinstance(e,R.Refused) else 'ENABLE_VALIDATION_ACTIONS_REFUSED'},sort_keys=True));return 1
 finally:os.close(fd)
if __name__=='__main__':raise SystemExit(main())
