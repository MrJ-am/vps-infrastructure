"""Exercise the installed bridge and root controller with an isolated empty queue."""
import json,os,stat,subprocess
from pathlib import Path
SD='/nix/store/0xiinbh7pbj479i5v28mqnjrvhvbdibf-systemd-260.2/bin'
PREP='/nix/store/viw2dxjfl93wwazydq9r9j7xz8xlpn92-mrjam-exact-intake-preparation-1'
CONTROL='/nix/store/kvdg4ir25db31mlchn2765nf3vqbpbxv-mrjam-protected-admission-controller-1'
STATE=Path('/var/lib/private/mrjam-intake-controller-qualification')
INBOX=Path('/var/lib/mrjam-intake-decisions-qualification')
def run(name,executable,properties):
    args=[SD+'/systemd-run','--quiet','--wait','--pipe','--unit='+name]
    for key,value in properties.items():
        for entry in value if type(value) is list else [value]:args+=['--property='+key+'='+entry]
    result=subprocess.run(args+[executable],capture_output=True,timeout=900)
    codes=[];details=[]
    for line in result.stdout.splitlines():
        try:
            value=json.loads(line);code=value.get('code','')
            if type(code) is str and len(code)<=80 and code.replace('_','').isupper():
                codes.append(code);details.append({k:value[k] for k in ('exception_type','source','line') if k in value})
        except Exception:pass
    if result.returncode:
        print(json.dumps({'code':'CONTROLLER_QUALIFICATION_UNIT_REFUSED','unit':name,'exit':result.returncode,'closed_codes':codes,'details':details}))
        raise SystemExit(2)
    return codes
def main():
    assert os.getuid()==0 and os.uname().nodename=='srv1982677'
    INBOX.mkdir(mode=0o755,exist_ok=True);INBOX.chmod(0o755)
    common={'Type':'oneshot','ProtectSystem':'strict','ProtectHome':'yes','PrivateDevices':'yes','NoNewPrivileges':'yes',
        'StateDirectoryMode':'0700','UMask':'0077','MemoryMax':'768M','TasksMax':'64','StandardError':'null',
        'RestrictAddressFamilies':'AF_UNIX AF_INET AF_INET6','TimeoutStartSec':'840'}
    prep={**common,'DynamicUser':'yes','User':'mrjam-intake-qual','StateDirectory':STATE.name,
        'CapabilityBoundingSet':'','TemporaryFileSystem':'/tmp:rw,size=512M,mode=1777',
        'LoadCredential':'github-app:/var/lib/mrjam-github-app/app-credentials.json',
        'Environment':'MRJAM_ADOPTED_BASE=/etc/mrjam-delivery-adopted.json MRJAM_INTAKE_DECISIONS='+str(INBOX)}
    codes=run('mrjam-controller-qualification-bridge',PREP+'/bin/mrjam-intake-prepare',prep)
    assert codes==['PREPARATION_IDLE']
    snapshot=json.loads((STATE/'ready.json').read_bytes());assert snapshot['ready']==[] and not snapshot['deployment_authorized']
    controller={**common,'User':'root','StateDirectory':'mrjam-admission-controller-qualification',
        'CapabilityBoundingSet':'CAP_DAC_READ_SEARCH','PrivateTmp':'yes',
        'ReadWritePaths':'/var/lib/mrjam-cutover/first-deployment/transaction.lock',
        'LoadCredential':['github-app:/var/lib/mrjam-github-app/app-credentials.json',
            'forgejo-dispatch:/var/lib/mrjam-ci-credentials/forgejo-registration-token'],
        'InaccessiblePaths':'-/var/lib/postgresql -/var/lib/kanidm -/var/lib/nextcloud -/var/lib/mrjam-validation-authority/signing-key -/var/lib/mrjam-github-app -/var/lib/mrjam-ci-credentials -/var/lib/mrjam-forgejo-runner/registration -/var/lib/mrjam-cutover/vise-adoption-20261103',
        'Environment':'MRJAM_INTAKE_STATE='+str(STATE)}
    observations=[]
    for number in (1,2):
        observed=run('mrjam-controller-qualification-'+str(number),CONTROL+'/bin/mrjam-admission-controller',controller)
        assert observed==['ORCHESTRATOR_IDLE'];observations.append(observed)
    jobs=Path('/var/lib/mrjam-admission-controller-qualification/jobs');assert jobs.is_dir() and not list(jobs.iterdir())
    print(json.dumps({'code':'LIVE_CONTROLLER_BRIDGE_QUALIFIED','root_observations':observations,'ready':0,
        'isolated_state':True,'new_admission':False,'new_dispatch':False,'deployment_performed':False}))
if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps({'code':'LIVE_CONTROLLER_QUALIFICATION_FAILED','exception_type':type(error).__name__}));raise SystemExit(2)
