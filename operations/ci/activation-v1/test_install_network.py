"""Run only inside an isolated user+network namespace; no production contact."""
import importlib.util,subprocess,sys
from pathlib import Path
spec=importlib.util.spec_from_file_location('install',Path(__file__).with_name('install_inactive.py'));A=importlib.util.module_from_spec(spec);spec.loader.exec_module(A)
need=lambda args:subprocess.run([A.NFT,*args],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
rules='table inet mrjam-forgejo-coordinator { chain bounded_output { type filter hook output priority 10; policy accept; meta skuid 950 ip daddr 127.0.0.1 tcp dport 3004 accept; meta skuid 950 reject; meta skuid 949 ip daddr 127.0.0.1 tcp dport 3004 accept; meta skuid 949 reject; }; }\n'
subprocess.run([A.NFT,'-f','-'],input=rules.encode(),check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
A.table(True)
need(['delete','table','inet','mrjam-forgejo-coordinator']);A.table(False)
subprocess.run([A.NFT,'-f','-'],input=rules.replace('3004','3005').encode(),check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
try:A.table(True)
except A.C.Refused:pass
else:raise AssertionError('wrong destination accepted')
print('PASS native nftables accept, absence and wrong-destination refusal')
