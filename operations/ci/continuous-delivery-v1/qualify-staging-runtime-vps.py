"""Read-only runtime qualification with the acceptance role's restricted rights."""
import json,os,subprocess,sys
from pathlib import Path
PACKAGE='/nix/store/zf97rkdq655qhfa9zijwyzvjinambdkv-mrjam-separated-acceptance-services-1'
LIBS=[PACKAGE+'/lib','/nix/store/qmzbv6zskr9qzhh3ifqs010jz26q2jlh-mrjam-protected-admission-controller-1/lib',
 '/nix/store/ixhqrvgq1vixg0g0fc01lwkdprxxkmn7-mrjam-validation-admission-control-1/lib']
sys.path[:0]=LIBS
import delivery_environment as E,staging_runtime as R,contract as C
SYSTEM='/nix/store/m01vhv8qwbaqs41ns64gkih8zwgvsbvw-nixos-system-srv1982677-26.05pre-git'
ROOT=Path('/var/lib/mrjam-staging-runtime-qualification-001')
PYTHON='/nix/store/kp6p38x6zb21n7gdlnp9nsm2aagq7sg2-python3-3.13.17/bin/python3'
RUN='/nix/store/0xiinbh7pbj479i5v28mqnjrvhvbdibf-systemd-260.2/bin/systemd-run'

def main():
    C.require(os.getuid()==0 and len(sys.argv)==1 and os.uname().nodename=='srv1982677','RUNTIME_QUALIFICATION_HOST_REFUSED')
    environment=E.read();C.require(environment['system']==SYSTEM,'RUNTIME_QUALIFICATION_BASELINE_REFUSED')
    slot='green' if environment['active_slot']=='blue' else 'blue'
    record=R.capture(slot,environment)
    ROOT.mkdir(mode=0o700)
    fd=os.open(ROOT/'record.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
    with os.fdopen(fd,'w') as out:json.dump(record,out)
    script='import sys,json;sys.path[:0]='+repr(LIBS)+'''
from pathlib import Path
import delivery_environment as E,staging_runtime as R
record=json.loads(Path('/var/lib/mrjam-staging-runtime-qualification-001/record.json').read_bytes())
R.verify(record,E.read())
print(json.dumps({'code':'STAGING_RUNTIME_RESTRICTED_PROBE_OK','readiness_verified':True,'process_identity_verified':True}))
'''
    properties=['User=root','ProtectSystem=strict','ProtectHome=true','PrivateTmp=true','PrivateDevices=true',
        'NoNewPrivileges=true','CapabilityBoundingSet=CAP_DAC_READ_SEARCH','ProtectControlGroups=true',
        'RestrictNamespaces=true','RestrictAddressFamilies=AF_UNIX AF_INET','IPAddressDeny=any','IPAddressAllow=localhost',
        'InaccessiblePaths=-/run/systemd/private -/run/dbus/system_bus_socket -/nix/var/nix/daemon-socket '
        '-/var/lib/postgresql -/var/lib/kanidm -/var/lib/nextcloud -/var/lib/forgejo -/var/lib/vise '
        '-/var/lib/mrjam-github-app -/var/lib/mrjam-ci-credentials -/var/lib/mrjam-delivery-credentials '
        '-/var/lib/mrjam-validation-authority -/run/secrets -/run/postgresql -/run/mrjam-identity',
        'MemoryMax=128M','CPUQuota=25%','TasksMax=16','RuntimeMaxSec=30']
    args=[RUN,'--quiet','--wait','--pipe','--unit=mrjam-staging-runtime-qualification-001']
    args += ['--property='+p for p in properties]
    result=subprocess.run(args+[PYTHON,'-I','-S','-c',script],stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45)
    C.require(result.returncode==0 and len(result.stdout)<=4096,'RUNTIME_QUALIFICATION_PROBE_FAILED')
    proof=json.loads(result.stdout);C.require(proof['code']=='STAGING_RUNTIME_RESTRICTED_PROBE_OK','RUNTIME_QUALIFICATION_OUTPUT_REFUSED')
    C.require(E.read()==environment,'RUNTIME_QUALIFICATION_ENVIRONMENT_CHANGED')
    R.verify(record,environment)
    proof.update(schema_version=1,package=PACKAGE,system=SYSTEM,slot=slot,activated=False,
        environment_unchanged=True,ptrace_capability=False,systemd_control_socket=False)
    print(json.dumps(proof,sort_keys=True))

if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps({'code':'RUNTIME_QUALIFICATION_FAILED','exception_type':type(error).__name__}))
        raise SystemExit(2) from None
