"""One repository runner bootstrap; owner lease is revoked before returning.

Forgejo 17 requires repository owner for runners, unlike branch protections.
The durable registrar account is not promoted. The immutable registration
contract runs as UID 949 with a temporary token passed only in process memory.
"""
import os, json, stat, fcntl, importlib.util, signal
from pathlib import Path
BOOTSTRAP='/nix/store/8pkxq7pahlmhlmf6v890q2ica69cflsy-mrjam-forgejo-technical-bootstrap-1/libexec/core.py'
REGISTRAR='/nix/store/y7shwh8rnvpsri88shhflp7av0l5hx4l-mrjam-forgejo-registration/register_runner.py'
CURRENT='/nix/store/i367qqkm6fzsr9rh8lbs2ymf53166hj9-nixos-system-srv1982677-26.05pre-git'
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def child(token,pipe):
 try:
  os.setgroups([]);os.setgid(949);os.setuid(949);os.umask(0o077)
  R=load('registrar',REGISTRAR)
  root=os.open(R.STATE,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
  info=os.fstat(root);R.api.require(info.st_uid==949 and stat.S_IMODE(info.st_mode)==0o700,'STATE_REFUSED')
  lock=os.open('operation.lock',os.O_RDWR|os.O_NOFOLLOW,dir_fd=root);fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  R.api.require(set(os.listdir(root))=={'operation.lock'},'REGISTRATION_ALREADY_STARTED')
  result=R.register(R.Transport(token),R.api.document(R.POLICY),None,lambda record,secret:R.store(root,record,secret))
  os.write(pipe,json.dumps(result).encode());os._exit(0)
 except BaseException:
  os.write(pipe,b'{"code":"BOOTSTRAP_REGISTRATION_REFUSED"}');os._exit(1)
def main():
 signal.alarm(180)
 assert os.geteuid()==0 and os.uname().nodename=='srv1982677' and os.path.realpath('/run/current-system')==CURRENT
 lock=os.open('/var/lib/mrjam-cutover/first-deployment/transaction.lock',os.O_RDWR|os.O_NOFOLLOW);fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 B=load('bootstrap',BOOTSTRAP)
 with B.governance_lease() as token:
  rd,wr=os.pipe();pid=os.fork()
  if pid==0:
   os.close(rd);child(token,wr)
  os.close(wr);raw=os.read(rd,8192);os.close(rd);_,status=os.waitpid(pid,0)
  result=json.loads(raw)
 result['temporary_owner_token_revoked']=True
 result['permanent_admin_grant']=False
 print(json.dumps(result,sort_keys=True))
 return os.waitstatus_to_exitcode(status)
if __name__=='__main__':raise SystemExit(main())
