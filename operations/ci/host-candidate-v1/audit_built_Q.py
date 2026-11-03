from pathlib import Path
import json,hashlib,subprocess,os,re
L=Path('.local/deployment-20261101');A=Path('/nix/store/phi68cwg38madbq8p805yvrsyry8g8wr-nixos-system-srv1982677-26.05pre-git');B=Path('/nix/store/g1l3zif8rwndmdcyc1vylwasaxds9iia-nixos-system-srv1982677-26.05pre-git');sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
apps=['forgejo','nginx','postgresql','kanidm','phpfpm-nextcloud','redis-nextcloud','mrjam-rust-blue','mrjam-rust-green','mrjam-identity','mrjam-identity-deletion','mrjam-vision-admission','mrjam-vision-archive','mrjam-vision-closure','mrjam-vision-cycle','mrjam-vision-replay','vision-embeddings','firewall','sshd']
for name in apps:assert (A/f'etc/systemd/system/{name}.service').read_bytes()==(B/f'etc/systemd/system/{name}.service').read_bytes(),name
assert (B/'etc/modprobe.d/nixos.conf').read_bytes()==b'blacklist ip_tables\n'+(A/'etc/modprobe.d/nixos.conf').read_bytes()
initrd=json.loads((L/'ci-initrd-Q-delta.json').read_text());assert set(initrd['changed'])=={'etc/modprobe.d/nixos.conf'} and len(initrd['added'])==len(initrd['removed'])==1
for p in ['kernel','kernel-modules','firmware']:
 if (A/p).exists():assert (A/p).resolve()==(B/p).resolve(),p
oldusers=Path('/nix/store/0sfj9b6sxa9f7g412lsgv3a1ic03zbbn-users-groups.json');newusers=Path('/nix/store/9dfpp4dfdjb2lwzzh3hmj4b28b4faay8-users-groups.json')
a=json.loads(oldusers.read_bytes());b=json.loads(newusers.read_bytes());assert a['mutableUsers']==b['mutableUsers'];added={}
for k in ['users','groups']:
 x={r['name']:r for r in a[k]};y={r['name']:r for r in b[k]};assert all(y.get(n)==r for n,r in x.items());added[k]=sorted(y.keys()-x.keys())
assert len(added['users'])==5 and len(added['groups'])==7
for name in ['activate','dry-activate','prepare-root','bin/switch-to-configuration']:
 old=(A/name).read_text();new=(B/name).read_text()
 for x,y in [(str(B),str(A)),(str((B/'etc').resolve()),str((A/'etc').resolve())),(str(newusers),str(oldusers))]:new=new.replace(x,y)
 assert new==old,name
assert sha(A/'bin/.switch-to-configuration-wrapped')==sha(B/'bin/.switch-to-configuration-wrapped')
bootold=json.loads((A/'boot.json').read_bytes());bootnew=json.loads((B/'boot.json').read_bytes())
for x,y in [(str(B),str(A)),(str((B/'initrd').resolve()),str((A/'initrd').resolve()))]:bootnew=json.loads(json.dumps(bootnew).replace(x,y))
assert bootnew==bootold
for name in ['dbus-1/session.conf','dbus-1/system.conf']:
 assert (B/'etc'/name).read_text().replace(str((B/'sw').resolve()),str((A/'sw').resolve()))==(A/'etc'/name).read_text()
oldtmp=(A/'etc/tmpfiles.d/00-nixos.conf').read_text().splitlines();newtmp=(B/'etc/tmpfiles.d/00-nixos.conf').read_text().splitlines();assert set(oldtmp)<=set(newtmp)
for p in (A/'sw/bin').iterdir():assert (B/'sw/bin'/p.name).resolve()==p.resolve()
assert {p.name for p in (B/'sw/bin').iterdir()}-{p.name for p in (A/'sw/bin').iterdir()}=={'nft'}
info=json.loads(subprocess.check_output(['nix','--extra-experimental-features','nix-command','path-info','--json',str(B)],stderr=subprocess.DEVNULL))[str(B)]
v={'schema_version':1,'scope':'built inactive CI host generation delta; not activation authority','source_revision':'e1dc4a31dc5a8ff37ab0639fb1af131e40263e4e','previous':str(A),'candidate':str(B),'candidate_nar_hash':info['narHash'],'application_and_firewall_ssh_units_byte_identical':apps,'new_identities':added,'activation_scripts_only_generation_etc_users_paths_changed':True,'kernel_modules_and_firmware_unchanged':True,'boot_spec_only_generation_and_initrd_changed':True,'initrd_entries_compared':initrd['old_entries'],'initrd_change':'only modprobe configuration symlink and referenced file; adds blacklist ip_tables, legacy module not iptables-nft','system_bin_only_added':['nft'],'existing_tmpfiles_rules_retained':True,'new_tmpfiles_rules':sorted(set(newtmp)-set(oldtmp)),'initrd_delta_sha256':sha(L/'ci-initrd-Q-delta.json'),'etc_delta_sha256':sha(L/'ci-host-Q-built-delta-001.json'),'build_log_sha256':sha(L/'ci-host-Q-build-001.log'),'coordinator_build_log_sha256':sha(L/'ci-coordinator-v3-build-001.log'),'limits':['No production activation or reboot is established.','All CI service/socket starts remain explicit; only nftables is newly wanted at boot.','Rollback must remove the dedicated output table without flushing existing INPUT or unrelated nftables tables.','Credentials are still absent; policy and runner activation are later operations.']}
Path('operations/ci/host-candidate-v1/qualification-built-Q-20261103-001.json').write_text(json.dumps(v,indent=2,sort_keys=True)+'\n');print(json.dumps({'checks':'passed','candidate':str(B),'nar_hash':info['narHash']}))
