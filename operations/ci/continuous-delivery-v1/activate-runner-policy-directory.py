"""Repair the runner policy mount and verify it across real host activation."""
import importlib.util,json,os,stat
from pathlib import Path
spec=importlib.util.spec_from_file_location('activation','@activation-driver@')
A=importlib.util.module_from_spec(spec);spec.loader.exec_module(A)
A.OLD='/nix/store/6yalib0qwm5yjrzhc1yrmnjdpjip8aqb-nixos-system-srv1982677-26.05pre-git'
A.NEW='/nix/store/zsfxxknh53v8s20v98m2b6ra9inl6471-nixos-system-srv1982677-26.05pre-git'
A.PACKAGE='/nix/store/viw2dxjfl93wwazydq9r9j7xz8xlpn92-mrjam-exact-intake-preparation-1'
A.JOURNAL=Path('/var/lib/mrjam-delivery-captures/runner-policy-directory-activation-002.json')
# The runner must restart to acquire its new mount namespace. Application
# processes retain the original driver's strict PID/state equality check.
A.UNITS.remove('mrjam-forgejo-runner.service')
original_run=A.run
def run(args,capture=False):
    result=original_run(args,capture)
    # The bootstrap intentionally sets restartIfChanged/stopIfChanged=false.
    # Restart this idle coordinator explicitly after each test/return switch.
    if args in [[A.NEW+'/bin/switch-to-configuration','test'],[A.OLD+'/bin/switch-to-configuration','test']]:
        original_run([A.CTL,'restart','mrjam-forgejo-runner'])
    return result
A.run=run
original_prepare=A.prepare
def policy():
    A.require(A.run([A.CTL,'is-active','mrjam-forgejo-runner'],True).strip()==b'active','RUNNER_INACTIVE')
    pid=int(A.run([A.CTL,'show','mrjam-forgejo-runner','-p','MainPID','--value'],True))
    host=Path('/etc/mrjam-forgejo-runner/admission.json')
    view=Path('/proc')/str(pid)/'root/etc/mrjam-forgejo-runner/admission.json'
    a=host.stat();b=view.stat()
    A.require((a.st_dev,a.st_ino)==(b.st_dev,b.st_ino) and b.st_nlink==1
        and b.st_uid==0 and stat.S_ISREG(b.st_mode) and not b.st_mode&0o222,'RUNNER_POLICY_STALE')
    A.require(set(p.name for p in host.parent.iterdir())=={'admission.json'},'RUNNER_POLICY_DIRECTORY_REFUSED')
    raw=host.read_bytes()
    A.require(raw==view.read_bytes() and json.loads(raw)=={'schema_version':1,
        'rules_revision':'b02bdf1b5d63dcf0e0610723788a7ca7e384932c'},'RUNNER_POLICY_CHANGED')
def prepare():
    result=original_prepare();policy();return result
A.prepare=prepare
def main():
    for path in Path('/var/lib/mrjam-intake-admission/jobs').glob('*/state.json'):
        A.require(json.loads(path.read_bytes())['phase'] not in {'admitted','dispatching','running'},'ACTIVE_CI_REFUSED')
    A.main();policy()
    print(json.dumps({'code':'RUNNER_POLICY_DIRECTORY_VERIFIED','policy_checks_unchanged':True,
        'real_return_verified':True,'automatic_deployment_enabled':False}))
if __name__=='__main__':main()
