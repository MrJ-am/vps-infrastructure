"""Restore the two prior admission/authority mounts without replacing others."""
import importlib.util,stat
from pathlib import Path
spec=importlib.util.spec_from_file_location('driver','/nix/store/5gxlbfkdcvzx3dsnlkrqpmc5gczr8pp9-mrjam-activate-runner-policy-directory/lib/main.py')
D=importlib.util.module_from_spec(spec);spec.loader.exec_module(D)
D.A.OLD='/nix/store/rks6y23zykcka5ifmilxj0p8r6nvrd57-nixos-system-srv1982677-26.05pre-git'
D.A.NEW='/nix/store/mp6b02wzn3pj5fn1g8j8gp9nzfr4fsq0-nixos-system-srv1982677-26.05pre-git'
D.A.JOURNAL=Path('/var/lib/mrjam-delivery-captures/runner-admission-mounts-activation-001.json')
original_policy=D.policy
def policy():
    original_policy()
    pid=int(D.A.run([D.A.CTL,'show','mrjam-forgejo-runner','-p','MainPID','--value'],True))
    root=Path('/proc')/str(pid)/'root'
    for name in ['var/lib/mrjam-validation-admissions','run/mrjam-validation-authority/request.sock']:
        host=Path('/')/name;view=root/name;a=host.stat();b=view.stat()
        D.A.require((a.st_dev,a.st_ino)==(b.st_dev,b.st_ino),'RUNNER_ADMISSION_MOUNT_REFUSED')
    D.A.require(stat.S_ISSOCK((root/'run/mrjam-validation-authority/request.sock').stat().st_mode),'RUNNER_AUTHORITY_SOCKET_REFUSED')
    digest='e06f030310aed4f8ff1cb0c5b836848dfcd9d4e99b926c841f7619b477fdd7e7'
    D.A.require((root/'var/lib/mrjam-validation-admissions'/ (digest+'.json')).is_file(),'RUNNER_DYNAMIC_ADMISSION_MISSING')
D.policy=policy
if __name__=='__main__':D.main()
