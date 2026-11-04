"""Install signed-result feedback while preserving applications and live CI."""
import importlib.util,json,stat
from pathlib import Path
spec=importlib.util.spec_from_file_location('activation','@activation-driver@')
A=importlib.util.module_from_spec(spec);spec.loader.exec_module(A)
A.OLD='/nix/store/zsfxxknh53v8s20v98m2b6ra9inl6471-nixos-system-srv1982677-26.05pre-git'
A.NEW='/nix/store/rks6y23zykcka5ifmilxj0p8r6nvrd57-nixos-system-srv1982677-26.05pre-git'
A.PACKAGE='/nix/store/viw2dxjfl93wwazydq9r9j7xz8xlpn92-mrjam-exact-intake-preparation-1'
A.JOURNAL=Path('/var/lib/mrjam-delivery-captures/validation-feedback-activation-001.json')
original_prepare=A.prepare
def check_runner():
    pid=int(A.run([A.CTL,'show','mrjam-forgejo-runner','-p','MainPID','--value'],True))
    host=Path('/etc/mrjam-forgejo-runner/admission.json')
    view=Path('/proc')/str(pid)/'root/etc/mrjam-forgejo-runner/admission.json'
    a=host.stat();b=view.stat()
    A.require((a.st_dev,a.st_ino)==(b.st_dev,b.st_ino) and b.st_nlink==1 and b.st_uid==0
        and stat.S_ISREG(b.st_mode) and not b.st_mode&0o222,'RUNNER_POLICY_STALE')
def prepare():
    result=original_prepare();check_runner()
    unit=Path('/etc/systemd/system/mrjam-admission-controller.service').read_text()
    A.require('/nix/store/dlphwj3kmxmljjg4dj6flihqah9jghgy-mrjam-protected-admission-controller-1/bin/mrjam-admission-controller' in unit,'FEEDBACK_PACKAGE_REFUSED')
    return result
A.prepare=prepare
original_run=A.run
def run(args,capture=False):
    result=original_run(args,capture)
    if args==[A.NEW+'/bin/switch-to-configuration','boot']:check_runner()
    return result
A.run=run
if __name__=='__main__':A.main()
