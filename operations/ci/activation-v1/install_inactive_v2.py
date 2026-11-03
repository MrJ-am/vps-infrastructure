"""Install the sealed inactive CI generation using the qualified return machine."""
import sys,os,json,subprocess,hashlib,pwd,grp
from pathlib import Path
sys.path.insert(0,'/nix/store/f0v9l1a6i7hj67y2mcwxa9h5i485gbnd-mrjam-resolver-update-001/libexec')
import resolver_update_adapter as A
import configuration_update as C
A.PREVIOUS='/nix/store/phi68cwg38madbq8p805yvrsyry8g8wr-nixos-system-srv1982677-26.05pre-git'
A.CANDIDATE='/nix/store/g1l3zif8rwndmdcyc1vylwasaxds9iia-nixos-system-srv1982677-26.05pre-git'
A.STAGED='/nix/store/dc09bjfaf8wsfrwxpkqw0bi3xhp3nklm-nixos-system-srv1982677-26.05pre-git'
A.STATE=Path('/var/lib/mrjam-cutover/ci-inactive-install-002')
A.CONFIG_HASH={p:'99b78f07d835746413e9ab4d044fe262fac63c4c58c938f05d6edf0028976636' for p in (A.PREVIOUS,A.CANDIDATE)}
BASE=A.Adapter
CI=['mrjam-forgejo-policy.service','mrjam-forgejo-registration.service','mrjam-forgejo-runner.service','mrjam-validation-staging.service','mrjam-validation-authority.service','mrjam-validation-worker.socket','mrjam-validation-collector.socket','mrjam-validation-export.socket','mrjam-validation-authority.socket']
APPS=['forgejo','nginx','postgresql','kanidm','phpfpm-nextcloud','redis-nextcloud','mrjam-rust-blue','mrjam-rust-green','mrjam-identity','mrjam-identity-deletion','mrjam-vision-admission','mrjam-vision-archive','mrjam-vision-closure','mrjam-vision-cycle','mrjam-vision-replay','vision-embeddings','firewall','sshd']
NFT='/nix/store/gripy5dbgwaa7g173vxdm6vr1vwhmk72-nftables-1.1.6/bin/nft'
def output(args):
 p=subprocess.run(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=15);C.require(len(p.stdout)<=65536,'OUTPUT_LIMIT');return p.returncode,p.stdout
def inactive():
 for name in CI:
  code,data=output([A.SYSTEMD+'systemctl','show',name,'--property=ActiveState','--value']);C.require(code==0 and data.strip() in (b'inactive',b'failed'),'CI_ALREADY_RUNNING')
def table(required):
 code,raw=output([NFT,'-j','list','table','inet','mrjam-forgejo-coordinator'])
 if not required:C.require(code!=0,'CI_TABLE_RETAINED');return
 C.require(code==0,'CI_TABLE_MISSING');rows=json.loads(raw)['nftables'];chains=[r['chain'] for r in rows if 'chain' in r];rules=[r['rule'] for r in rows if 'rule' in r]
 C.require(len(chains)==1 and chains[0]['name']=='bounded_output' and chains[0]['hook']=='output' and chains[0]['prio']==10 and chains[0]['policy']=='accept','CI_CHAIN_REFUSED')
 C.require(len(rules)==4,'CI_RULES_REFUSED')
 for row,uid,accept in zip(rules,[950,950,949,949],[True,False,True,False]):
  e=row['expr'];C.require(row['chain']=='bounded_output' and e[0]=={'match':{'op':'==','left':{'meta':{'key':'skuid'}},'right':uid}},'CI_UID_REFUSED')
  if accept:
   C.require(e[1:]==[{'match':{'op':'==','left':{'payload':{'protocol':'ip','field':'daddr'}},'right':'127.0.0.1'}},{'match':{'op':'==','left':{'payload':{'protocol':'tcp','field':'dport'}},'right':3004}},{'accept':None}],'CI_ALLOW_REFUSED')
  else:C.require(len(e)==2 and set(e[1])=={'reject'},'CI_DENY_REFUSED')
class Adapter(BASE):
 def preflight(self):
  C.require(os.uname().nodename=='srv1982677','HOST_REFUSED');super().preflight();inactive()
  for uid,name in enumerate(['mrjam-forgejo-registration','mrjam-forgejo-runner','mrjam-validation-worker','mrjam-validation-collector','mrjam-validation-authority'],949):
   try:entry=pwd.getpwuid(uid)
   except KeyError:pass
   else:C.require(entry.pw_name==name and entry.pw_gid==uid,'UID_COLLISION')
   try:entry=pwd.getpwnam(name)
   except KeyError:pass
   else:C.require(entry.pw_uid==uid and entry.pw_gid==uid,'ACCOUNT_COLLISION')
  for gid,name in enumerate(['mrjam-forgejo-registration','mrjam-forgejo-runner','mrjam-validation-worker','mrjam-validation-collector','mrjam-validation-authority','mrjam-validation-submitters','mrjam-validation-requesters'],949):
   try:entry=grp.getgrgid(gid)
   except KeyError:pass
   else:C.require(entry.gr_name==name,'GID_COLLISION')
  for name in APPS:
   p='etc/systemd/system/'+name+'.service';C.require((Path(A.PREVIOUS)/p).read_bytes()==(Path(A.CANDIDATE)/p).read_bytes(),'APPLICATION_UNIT_CHANGED')
 def verify(self,generation):
  super().verify(generation);inactive();table(generation==A.CANDIDATE)
  if generation==A.CANDIDATE:
   for name in CI:
    p=Path('/etc/systemd/system')/name;C.require(p.resolve()==(Path(A.CANDIDATE)/'etc/systemd/system'/name).resolve(),'CI_UNIT_CHANGED')
   A.run([A.SYSTEMD+'systemctl','is-active','--quiet','nftables.service'])
A.Adapter=Adapter
if __name__=='__main__':
 import fcntl,re,traceback
 events=[]
 def wrap(name):
  original=getattr(Adapter,name)
  def call(self,*args):
   try:result=original(self,*args);events.append({'stage':name,'passed':True});return result
   except Exception as e:
    events.append({'stage':name,'passed':False,'code':str(e) if re.fullmatch('[A-Z_]{1,80}',str(e)) else type(e).__name__});raise
  setattr(Adapter,name,call)
 for name in ['preflight','activate_candidate','verify_candidate','select_candidate_boot','activate_previous','select_previous_boot','verify_previous']:wrap(name)
 os.umask(0o077)
 fd=os.open(str(A.LOCK),os.O_RDWR|os.O_NOFOLLOW);fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
 try:
  code=C.update(Adapter());print(json.dumps({'schema_version':1,'code':code,'events':events}));sys.exit(0 if code in ('CONFIGURATION_VERIFIED','CONFIGURATION_ALREADY_VERIFIED') else 1)
 except Exception as e:
  print(json.dumps({'schema_version':1,'code':str(e) if re.fullmatch('[A-Z_]{1,80}',str(e)) else type(e).__name__,'events':events}));sys.exit(1)
 finally:os.close(fd)
