"""Read-only ViSe unit/account/ledger metadata. Never read application records."""
import os,pwd,stat,json,subprocess
from pathlib import Path
S='/nix/store/0xiinbh7pbj479i5v28mqnjrvhvbdibf-systemd-260.2/bin/systemctl'
def main():
 assert os.geteuid()==0 and os.uname().nodename=='srv1982677'
 result={'schema_version':1,'code':'VISE_HOST_METADATA','current':os.path.realpath('/run/current-system')}
 try:
  account=pwd.getpwnam('etp_carnet');result['account']={'present':True,'uid':account.pw_uid,'gid':account.pw_gid}
 except KeyError:result['account']={'present':False}
 for name,path in [('state','/var/lib/etp-carnet'),('deletion_ledger','/var/lib/etp-carnet/deletions.log')]:
  try:
   m=Path(path).lstat();result[name]={'present':True,'regular':stat.S_ISREG(m.st_mode),'directory':stat.S_ISDIR(m.st_mode),'uid':m.st_uid,'gid':m.st_gid,'mode':oct(stat.S_IMODE(m.st_mode)),'single_link':m.st_nlink==1,'within_64_mib':m.st_size<=67108864}
  except FileNotFoundError:result[name]={'present':False}
 p=subprocess.run([S,'show','vise.service','-p','LoadState','-p','ActiveState','-p','SubState'],capture_output=True,timeout=10)
 result['unit']=dict(l.split('=',1) for l in p.stdout.decode().splitlines() if '=' in l)
 print(json.dumps(result,sort_keys=True))
if __name__=='__main__':main()
