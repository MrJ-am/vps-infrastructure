import os,json,subprocess
from pathlib import Path
assert os.geteuid()==0 and os.uname().nodename=='srv1982677'
s='/nix/store/0xiinbh7pbj479i5v28mqnjrvhvbdibf-systemd-260.2/bin/systemctl'
p=subprocess.run([s,'show','vise.service','-p','LoadState','-p','ActiveState','-p','FragmentPath','-p','SourcePath'],capture_output=True,timeout=10)
assert p.returncode==0 and len(p.stdout)<4096
v={'code':'VISE_STAGING_METADATA','unit':dict(x.split('=',1) for x in p.stdout.decode().splitlines() if '=' in x),'current':os.path.realpath('/run/current-system'),'boot':os.path.realpath('/nix/var/nix/profiles/system'),'postgresql_configuration':os.path.realpath('/var/lib/postgresql/17/postgresql.conf')}
base=Path('/var/lib/acme/.lego/vise.mrj.am')
v['certificate_state_directories']=sorted(x.name for x in base.iterdir() if x.is_dir() and len(x.name)==20) if base.is_dir() else []
v['retained_certificate_present']=Path('/var/lib/acme/vise.mrj.am/fullchain.pem').is_file()
v['retained_key_present']=Path('/var/lib/acme/vise.mrj.am/key.pem').is_file()
print(json.dumps(v,sort_keys=True))
