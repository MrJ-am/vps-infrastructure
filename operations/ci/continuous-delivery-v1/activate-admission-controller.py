"""Use the qualified return/boot transaction for the controller-only addition."""
import contextlib,importlib.util,io,json,re
from pathlib import Path
spec=importlib.util.spec_from_file_location('activation','@activation-driver@')
A=importlib.util.module_from_spec(spec);spec.loader.exec_module(A)
A.OLD='/nix/store/qjkig4qypn3640v2i9gb1qi4w0r48hj6-nixos-system-srv1982677-26.05pre-git'
A.NEW='/nix/store/a4hd5y55m2z7xh5na712bp4v22lyr1qr-nixos-system-srv1982677-26.05pre-git'
A.PACKAGE='/nix/store/viw2dxjfl93wwazydq9r9j7xz8xlpn92-mrjam-exact-intake-preparation-1'
A.JOURNAL=Path('/var/lib/mrjam-delivery-captures/admission-controller-activation-001.json')
CONTROL='/nix/store/kvdg4ir25db31mlchn2765nf3vqbpbxv-mrjam-protected-admission-controller-1'
original_prepare=A.prepare

def prepare():
    states=original_prepare()
    snapshot=json.loads((A.STATE/'ready.json').read_bytes())
    A.require(snapshot['schema_version']==1 and snapshot['deployment_authorized'] is False
        and len(snapshot['ready'])==states.get('ready',0),'CONTROLLER_BRIDGE_REQUIRED')
    unit=Path('/etc/systemd/system/mrjam-admission-controller.service').read_text()
    A.require(CONTROL+'/bin/mrjam-admission-controller' in unit,'CONTROLLER_EXECUTABLE_REFUSED')
    A.require(A.run([A.CTL,'is-active','mrjam-admission-controller.timer'],True).strip()==b'active','CONTROLLER_TIMER_INACTIVE')
    return states
A.prepare=prepare

def main():
    buffer=io.StringIO()
    try:
        with contextlib.redirect_stdout(buffer):A.main()
    except BaseException:
        print(buffer.getvalue(),end='');raise
    result=json.loads(buffer.getvalue());result['code']='ADMISSION_CONTROLLER_ACTIVE'
    # A.main has now released the adoption lock. Exercise the real root unit.
    A.run([A.CTL,'start','mrjam-admission-controller.service'])
    A.require(A.run([A.CTL,'show','mrjam-admission-controller.service','-p','Result','--value'],True).strip()==b'success','CONTROLLER_SERVICE_FAILED')
    invocation=A.run([A.CTL,'show','mrjam-admission-controller.service','-p','InvocationID','--value'],True).decode().strip()
    A.require(re.fullmatch('[0-9a-f]{32}',invocation),'CONTROLLER_INVOCATION_REFUSED')
    raw=A.run(['/nix/store/0xiinbh7pbj479i5v28mqnjrvhvbdibf-systemd-260.2/bin/journalctl',
        '--no-pager','-o','cat','_SYSTEMD_INVOCATION_ID='+invocation],True)
    codes=[]
    for line in raw.splitlines():
        try:
            code=json.loads(line).get('code','')
            if type(code) is str and re.fullmatch('[A-Z_]{1,80}',code):codes.append(code)
        except Exception:pass
    A.require(codes and all(code in {'ORCHESTRATOR_IDLE','ORCHESTRATOR_ADVANCED'} for code in codes),'CONTROLLER_EXECUTION_REFUSED')
    A.checkpoint('admission-controller-active-and-boot')
    result.update(controller_codes=codes,automatic_ci_configured=True,automatic_deployment_enabled=False)
    print(json.dumps(result))

if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps({'code':str(error) if isinstance(error,RuntimeError) else 'CONTROLLER_ACTIVATION_FAILED'}));raise SystemExit(2)
