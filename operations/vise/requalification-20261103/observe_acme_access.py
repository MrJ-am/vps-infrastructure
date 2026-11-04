import json,os,pwd,grp
from pathlib import Path
p=pwd.getpwnam('acme');g=grp.getgrnam('nginx');os.setgroups([]);os.setgid(g.gr_gid);os.setuid(p.pw_uid)
a=Path('/var/lib/acme/.lego/accounts/a96772ab152e39f749f9');c=Path('/var/lib/acme/.lego/vise.mrj.am/748661661a99cbbf91d5');out=Path('/var/lib/acme/vise.mrj.am')
v={'account_traversable':os.access(a,os.R_OK|os.X_OK),'certificate_directory_writable':os.access(c,os.W_OK|os.X_OK),'output_directory_writable':os.access(out,os.W_OK|os.X_OK),'challenge_writable':os.access('/var/lib/acme/acme-challenge',os.W_OK|os.X_OK),'serialization_writable':os.access('/run/mrjam-acme',os.W_OK|os.X_OK)}
keys=list(a.rglob('*.key'));v['one_account_key']=len(keys)==1
if len(keys)==1:
 k=keys[0];v['account_key_readable']=os.access(k,os.R_OK);v['registration_readable']=os.access(k.parent.parent/'account.json',os.R_OK)
v['certificate_files_readable']={e:os.access(c/('vise.mrj.am.'+e),os.R_OK) for e in ['crt','key','json','issuer.crt']}
v['output_files_readable']={e:os.access(out/e,os.R_OK) for e in ['fullchain.pem','key.pem']}
print(json.dumps({'code':'VISE_ACME_ACCESS_METADATA','checks':v},sort_keys=True))
