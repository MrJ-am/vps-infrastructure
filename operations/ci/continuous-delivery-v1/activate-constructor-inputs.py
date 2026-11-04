"""Retain fixed constructor inputs; reuse the qualified return/boot transaction."""
import importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location('activation','@activation-driver@')
A=importlib.util.module_from_spec(spec);spec.loader.exec_module(A)
A.OLD='/nix/store/a4hd5y55m2z7xh5na712bp4v22lyr1qr-nixos-system-srv1982677-26.05pre-git'
A.NEW='/nix/store/6yalib0qwm5yjrzhc1yrmnjdpjip8aqb-nixos-system-srv1982677-26.05pre-git'
A.PACKAGE='/nix/store/viw2dxjfl93wwazydq9r9j7xz8xlpn92-mrjam-exact-intake-preparation-1'
A.JOURNAL=Path('/var/lib/mrjam-delivery-captures/constructor-inputs-activation-001.json')
original_prepare=A.prepare
def prepare():
    state=original_prepare()
    unit=Path('/etc/systemd/system/mrjam-admission-controller.service').read_text()
    A.require('/nix/store/kypw185n5fsch7lynnriirc311md7ajj-mrjam-protected-admission-controller-1/bin/mrjam-admission-controller' in unit,'CONTROLLER_PACKAGE_REFUSED')
    A.require(A.run([A.CTL,'is-active','mrjam-admission-controller.timer'],True).strip()==b'active','CONTROLLER_TIMER_INACTIVE')
    return state
A.prepare=prepare
if __name__=='__main__':A.main()
