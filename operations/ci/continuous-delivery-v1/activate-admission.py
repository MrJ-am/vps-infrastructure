"""Fixed CI-only test activation and verified return; boot profile stays old."""
import fcntl,json,os,subprocess,time
from pathlib import Path

OLD='/nix/store/xqbbs66wf4q9n7fdrs9p54bf87ak264a-nixos-system-srv1982677-26.05pre-git'
NEW='/nix/store/frha1lc5vwqx4d5bzs6p2hfabk8r6r49-nixos-system-srv1982677-26.05pre-git'
PUBLISH='/nix/store/7icx05ykrz7fcqq1qz56zdl6xfmvdgpx-mrjam-publish-fixed-admission-1/bin/mrjam-publish-fixed-admission'
PROPOSAL='04754e2c5e531c37bd06864ed2becb3fc218d20d780d9a8c8e1b045956a5d04d'
CTL='/nix/store/0xiinbh7pbj479i5v28mqnjrvhvbdibf-systemd-260.2/bin/systemctl'
PROFILE='/nix/var/nix/profiles/system'
RUNNER='mrjam-forgejo-runner.service'
INHIBITOR=Path('/run/systemd/system/mrjam-forgejo-runner.service.d/90-mrjam-admission-transition.conf')
UNITS=['nginx.service','postgresql.service','forgejo.service','vise.service','mrjam-rust-blue.service','mrjam-rust-green.service']

def require(value,code):
    if not value:raise RuntimeError(code)

def run(argv,timeout=180,capture=False):
    result=subprocess.run(argv,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL,timeout=timeout)
    require(result.returncode==0,'COMMAND_FAILED')
    if capture:
        require(len(result.stdout)<=65536,'OBSERVATION_TOO_LARGE')
        return result.stdout

def properties(unit):
    raw=run([CTL,'show',unit,'-p','ActiveState','-p','SubState','-p','MainPID'],capture=True)
    return dict(line.split('=',1) for line in raw.decode().splitlines() if '=' in line)

def retained():return {unit:properties(unit) for unit in UNITS}

def idle():
    raw=run([CTL,'list-units','--state=active,activating,deactivating','--type=service','--output=json',
             'mrjam-validation-worker@*.service','mrjam-validation-collector@*.service',
             'mrjam-validation-export@*.service','mrjam-validation-authority.service'],capture=True)
    require(json.loads(raw)==[],'VALIDATION_BUSY')

def publish():
    # The persistent host uses RemainAfterExit=yes; start would reuse the old
    # completed publication instead of reading the newly installed catalogue.
    run([CTL,'restart','mrjam-validation-staging.service'])
    result=json.loads(run([PUBLISH],capture=True))
    require(result=={'code':'FIXED_ADMISSION_PUBLISHED','proposal_sha256':PROPOSAL},'PUBLICATION_REFUSED')

def release_inhibitor():
    INHIBITOR.unlink()
    run([CTL,'daemon-reload'])

def main():
    require(os.getuid()==0,'ADMIN_REQUIRED')
    lock=os.open('/run/mrjam-admission-activation.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    require(os.path.realpath('/run/current-system')==OLD and os.path.realpath(PROFILE)==OLD,'BASELINE_CHANGED')
    require(Path(NEW+'/bin/switch-to-configuration').is_file() and Path(PUBLISH).is_file(),'CANDIDATE_ABSENT')
    before=retained()
    require(all(before[name]['ActiveState']=='active' for name in UNITS if name!='mrjam-rust-green.service'),'RETAINED_SERVICE_NOT_ACTIVE')
    require(properties(RUNNER)['ActiveState']=='active','RUNNER_NOT_ACTIVE')
    require(not INHIBITOR.exists() and not INHIBITOR.is_symlink()
            and not Path('/run/mrjam-admission-transition-ready').exists(),'TRANSITION_ALREADY_PRESENT')
    idle()
    stage='quiesce-coordinator'
    try:
        INHIBITOR.parent.mkdir(mode=0o755,parents=True,exist_ok=True)
        with INHIBITOR.open('x') as out:
            out.write('[Unit]\nConditionPathExists=/run/mrjam-admission-transition-ready\n')
        run([CTL,'daemon-reload'])
        run([CTL,'stop',RUNNER]);idle()
        stage='test-new-configuration'
        run([NEW+'/bin/switch-to-configuration','test'])
        require(os.path.realpath('/run/current-system')==NEW and retained()==before,'NEW_CONFIGURATION_REFUSED')
        stage='stage-and-publish'
        publish()
        stage='exercise-configuration-return'
        run([OLD+'/bin/switch-to-configuration','test'])
        require(os.path.realpath('/run/current-system')==OLD and retained()==before,'CONFIGURATION_RETURN_FAILED')
        require(os.path.realpath(PROFILE)==OLD,'BOOT_PROFILE_CHANGED')
        stage='reapply-and-start'
        run([NEW+'/bin/switch-to-configuration','test'])
        publish()
        release_inhibitor()
        run([CTL,'start',RUNNER]);time.sleep(2)
        require(properties(RUNNER)['ActiveState']=='active','NEW_COORDINATOR_FAILED')
        require(os.path.realpath('/run/current-system')==NEW and retained()==before,'RETAINED_PROCESS_CHANGED')
        require(os.path.realpath(PROFILE)==OLD,'BOOT_PROFILE_CHANGED')
        print(json.dumps({'code':'ADMISSION_TEST_ACTIVE','current':NEW,'boot':OLD,
            'configuration_return_verified':True,'retained_processes_unchanged':True,
            'proposal_sha256':PROPOSAL,'production_validation_job_verified':False,
            'automatic_deployment_enabled':False},sort_keys=True))
    except Exception as failure:
        restored=False
        try:
            run([CTL,'stop',RUNNER]);run([OLD+'/bin/switch-to-configuration','test'])
            if INHIBITOR.exists():release_inhibitor()
            run([CTL,'start',RUNNER])
            restored=os.path.realpath('/run/current-system')==OLD and os.path.realpath(PROFILE)==OLD and retained()==before
        except Exception:pass
        print(json.dumps({'code':'ADMISSION_ACTIVATION_FAILED','stage':stage,
            'failure':str(failure) if isinstance(failure,RuntimeError) else type(failure).__name__,
            'configuration_return_verified':restored},sort_keys=True))
        raise SystemExit(1) from None
    finally:os.close(lock)

if __name__=='__main__':
    try:main()
    except Exception:
        print('{"code":"ADMISSION_PREFLIGHT_REFUSED"}');raise SystemExit(1) from None
