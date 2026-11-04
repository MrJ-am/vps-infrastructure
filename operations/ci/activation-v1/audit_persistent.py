"""Check built boot wiring byte deltas, including every service security field."""
from pathlib import Path
import json
OLD=Path('/nix/store/i367qqkm6fzsr9rh8lbs2ymf53166hj9-nixos-system-srv1982677-26.05pre-git')
NEW=Path('/nix/store/3fylc2yfjvzzibpi0pf0nzqj0f5lh1hm-nixos-system-srv1982677-26.05pre-git')
SOCKETS=['mrjam-validation-'+n+'.socket' for n in ['worker','collector','export','authority']]
def unit(root,name):return (root/'etc/systemd/system'/name).read_text()
for n in SOCKETS:
 assert unit(NEW,n)==unit(OLD,n)+'\n[Install]\nWantedBy=sockets.target\n',n
 assert (NEW/'etc/systemd/system/sockets.target.wants'/n).resolve()==(NEW/'etc/systemd/system'/n).resolve()
n='mrjam-validation-staging.service'
assert unit(NEW,n).replace('RemainAfterExit=true\n','')==unit(OLD,n)
n='mrjam-forgejo-runner.service'
for directive in ['After=','Requires=']:
 old=next(l for l in unit(OLD,n).splitlines() if l.startswith(directive)).split('=',1)[1].split()
 new=next(l for l in unit(NEW,n).splitlines() if l.startswith(directive)).split('=',1)[1].split()
 assert set(new)==set(old)|set(SOCKETS)|{'forgejo.service','mrjam-validation-staging.service'}
def strip(s):return '\n'.join(l for l in s.splitlines() if l and not l.startswith(('After=','Requires=','WantedBy=')) and l!='[Install]')
assert strip(unit(OLD,n))==strip(unit(NEW,n))
assert (NEW/'etc/systemd/system/multi-user.target.wants'/n).resolve()==(NEW/'etc/systemd/system'/n).resolve()
changed=[]
for p in (OLD/'etc/systemd/system').iterdir():
 if p.is_file() and p.suffix in ('.service','.socket') and p.read_bytes()!=(NEW/'etc/systemd/system'/p.name).read_bytes():changed.append(p.name)
assert sorted(changed)==sorted(SOCKETS+['mrjam-forgejo-runner.service','mrjam-validation-staging.service'])
for n in ['kernel','initrd','kernel-modules','firmware']:
 if (OLD/n).exists():assert (OLD/n).resolve()==(NEW/n).resolve()
print(json.dumps({'code':'CI_BOOT_WIRING_AUDITED','changed_units':sorted(changed),'execution_and_security_directives_unchanged':True,'application_units_unchanged':True,'boot_links_verified':True},sort_keys=True))
