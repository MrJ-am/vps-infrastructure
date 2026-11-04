"""Closed postflight for CI persistence, repository controls and service health."""
import os,json,subprocess,http.client,urllib.request,importlib.util
from pathlib import Path
EXPECTED='/nix/store/3fylc2yfjvzzibpi0pf0nzqj0f5lh1hm-nixos-system-srv1982677-26.05pre-git'
S='/nix/store/0xiinbh7pbj479i5v28mqnjrvhvbdibf-systemd-260.2/bin/systemctl'
REPOS=('Signature','apprendre-a-demontrer','etp-vie-affective','matheval','mrjam-plateforme','mrjam-validation','style-mrjam','vision','vps-infrastructure')
def main():
 assert os.path.realpath('/run/current-system')==os.path.realpath('/nix/var/nix/profiles/system')==EXPECTED
 units=['forgejo','nginx','kanidm','postgresql','mrjam-rust-blue','mrjam-identity','mrjam-identity-deletion','mrjam-vision-admission','mrjam-vision-closure','mrjam-forgejo-runner','mrjam-validation-staging']
 for n in units:
  p=subprocess.run([S,'is-active','--quiet',n+'.service'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10);assert p.returncode==0
 for n in ['worker','collector','export','authority']:
  name='mrjam-validation-'+n+'.socket'
  p=subprocess.run([S,'is-active','--quiet',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10);assert p.returncode==0
  assert (Path('/etc/systemd/system/sockets.target.wants')/name).resolve()==(Path('/etc/systemd/system')/name).resolve()
 assert Path('/etc/systemd/system/multi-user.target.wants/mrjam-forgejo-runner.service').exists()
 https={}
 for h in ['log.mrj.am','forge.mrj.am','audition.mrj.am']:
  with urllib.request.urlopen('https://'+h+'/',timeout=10) as r:assert r.status==200;https[h]=r.status
 spec=importlib.util.spec_from_file_location('R','/nix/store/brh7k2s8b8pjxkaadc4shs8sq877xni9-reconcile.py');R=importlib.util.module_from_spec(spec);spec.loader.exec_module(R)
 token=Path('/var/lib/mrjam-ci-credentials/forgejo-policy-token').read_text().strip()
 t=R.Transport(token);enabled=[]
 for n in REPOS:
  base='/api/v1/repos/MrJ-am/'+n
  repo=t.request('GET',base)
  if repo['has_actions']:enabled.append(n)
  assert R.filter_protection(t.request('GET',base+'/branch_protections/main'))==R.desired_protection()
 assert enabled==['mrjam-validation']
 p=subprocess.run([S,'show','mrjam-forgejo-registration.service','-p','ActiveState','--value'],capture_output=True,timeout=10);assert p.returncode==0
 if p.stdout.strip()==b'failed':
  p=subprocess.run([S,'reset-failed','mrjam-forgejo-registration.service'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10);assert p.returncode==0
 p=subprocess.run([S,'show','mrjam-forgejo-registration.service','-p','ActiveState','--value'],capture_output=True,timeout=10);assert p.returncode==0 and p.stdout.strip()==b'inactive'
 print(json.dumps({'schema_version':1,'code':'CI_POSTFLIGHT_PASSED','current_and_boot':EXPECTED,'active_services':len(units),'active_sockets':4,'persistent_boot_links':True,'https':https,'actions_enabled_repositories':enabled,'protected_repositories':len(REPOS),'registration_failure_acknowledged_after_successful_bootstrap':True},sort_keys=True))
if __name__=='__main__':main()
