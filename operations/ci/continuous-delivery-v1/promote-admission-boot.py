"""Persist only the already running, accepted CI generation; no app release."""
import fcntl,http.client,json,os,subprocess,sys
from pathlib import Path
sys.path.insert(0,'/nix/store/ixhqrvgq1vixg0g0fc01lwkdprxxkmn7-mrjam-validation-admission-control-1/lib')
import admission_control as R
import contract as C
import signer as A
OLD='/nix/store/xqbbs66wf4q9n7fdrs9p54bf87ak264a-nixos-system-srv1982677-26.05pre-git'
NEW='/nix/store/frha1lc5vwqx4d5bzs6p2hfabk8r6r49-nixos-system-srv1982677-26.05pre-git'
PROFILE='/nix/var/nix/profiles/system'
PROPOSAL='04754e2c5e531c37bd06864ed2becb3fc218d20d780d9a8c8e1b045956a5d04d'
ATTESTATION_SHA='645cbd33f82d0be8dbc2eef6990ba854a3610d96476c83dc922265b7f46a1e01'
CTL='/nix/store/0xiinbh7pbj479i5v28mqnjrvhvbdibf-systemd-260.2/bin/systemctl'
UNITS=['nginx.service','postgresql.service','forgejo.service','vise.service','mrjam-rust-blue.service','mrjam-rust-green.service','mrjam-forgejo-runner.service']

def run(args,capture=False):
    result=subprocess.run(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL,timeout=180)
    C.require(result.returncode==0,'BOOT_COMMAND_FAILED')
    if capture:C.require(len(result.stdout)<=65536,'OBSERVATION_LIMIT');return result.stdout

def retained():
    return {unit:run([CTL,'show',unit,'-p','MainPID','-p','ActiveState','-p','SubState'],True).decode() for unit in UNITS}

def main():
    C.require(os.getuid()==0 and os.uname().nodename=='srv1982677','HOST_REFUSED')
    lock=os.open('/run/mrjam-admission-activation.lock',os.O_RDWR|os.O_NOFOLLOW)
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    C.require(os.path.realpath('/run/current-system')==NEW and os.path.realpath(PROFILE)==OLD,'BASELINE_CHANGED')
    policy=R.load(PROPOSAL)['authority']
    raw=C.regular_file(Path('/var/lib/mrjam-forgejo-runner/attestations')/(PROPOSAL+'.json'),owner=policy['requester_uid'],mode=0o400,maximum=C.MAX_DOCUMENT)
    C.require(C.sha(raw)==ATTESTATION_SHA and A.verify(C.parse(raw),policy),'ATTESTATION_REFUSED')
    token=C.regular_file('/var/lib/mrjam-ci-credentials/forgejo-registration-token',owner=0,mode=0o400,maximum=4096).decode().strip()
    connection=http.client.HTTPConnection('127.0.0.1',3004,timeout=5)
    try:
        connection.request('GET','/api/v1/repos/MrJ-am/mrjam-validation/actions/runs/2',headers={'Authorization':'token '+token})
        response=connection.getresponse();raw=response.read(131073)
        C.require(response.status==200 and len(raw)<=131072 and json.loads(raw).get('status')=='success','JOB_NOT_SUCCESSFUL')
    finally:connection.close()
    before=retained();changed=False
    try:
        changed=True
        run(['/run/current-system/sw/bin/nix-env','--profile',PROFILE,'--set',NEW])
        run([NEW+'/bin/switch-to-configuration','boot'])
        C.require(os.path.realpath(PROFILE)==NEW and os.path.realpath('/run/current-system')==NEW,'BOOT_PROFILE_REFUSED')
        C.require(retained()==before,'RETAINED_PROCESS_CHANGED')
        print(json.dumps({'code':'ACCEPTED_CI_ACTIVE_AND_BOOT','current':NEW,'boot':NEW,'job_id':2,
                          'attestation_sha256':ATTESTATION_SHA,'retained_processes_unchanged':True,
                          'application_release_performed':False,'automatic_deployment_enabled':False},sort_keys=True))
    except Exception:
        restored=False
        if changed:
            try:
                run(['/run/current-system/sw/bin/nix-env','--profile',PROFILE,'--set',OLD])
                run([OLD+'/bin/switch-to-configuration','boot'])
                restored=os.path.realpath(PROFILE)==OLD and retained()==before
            except Exception:pass
        print(json.dumps({'code':'CI_BOOT_PROMOTION_FAILED','previous_boot_restored':restored}))
        raise SystemExit(1) from None
    finally:os.close(lock)

if __name__=='__main__':
    try:main()
    except Exception:
        print('{"code":"CI_BOOT_PREFLIGHT_REFUSED"}');raise SystemExit(1) from None
