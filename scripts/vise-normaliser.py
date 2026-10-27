"""Remove activation-only restart guards from the persisted ViSe adapter.
No activation, restart, SQL or other project file is touched.
"""
import json,pathlib,subprocess
p=pathlib.Path('/etc/nixos/vise-hosting/module.nix')
s=p.read_text()
lines=['  systemd.services.postgresql.'+k+' = lib.mkForce false;\n' for k in ('restartIfChanged','reloadIfChanged','stopIfChanged')]
assert all(s.count(line)==1 for line in lines)
assert 'https://vise.mrj.am' in s
before=subprocess.check_output(['systemctl','show','vise','postgresql','mrjam-metier','kanidm','forgejo','-p','MainPID'],text=True)
for line in lines:s=s.replace(line,'')
p.write_text(s)
after=subprocess.check_output(['systemctl','show','vise','postgresql','mrjam-metier','kanidm','forgejo','-p','MainPID'],text=True)
assert before==after
print(json.dumps({'activationOnlyGuardsRemoved':True,'servicesRestarted':False,'sqlChanged':False}))
