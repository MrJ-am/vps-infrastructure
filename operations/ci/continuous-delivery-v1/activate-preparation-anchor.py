"""Replace only the preparation worker after verifying the exact validated job."""
import fcntl,json,os,re,stat,subprocess,sys
from pathlib import Path
OLD='/nix/store/9vpbs7mxmz13k7mf4y7m20r6cvmn661y-nixos-system-srv1982677-26.05pre-git'
BOOT=OLD
NEW='/nix/store/459b63mrbil3n5ya27d7w1x8vas4za3k-nixos-system-srv1982677-26.05pre-git'
PREPARER='/nix/store/aij7vndm5yqsm98bh1n7bccb3gp2z0hn-mrjam-delivery-preparation-1/bin/mrjam-delivery-prepare'
PACKAGE='/nix/store/qmzbv6zskr9qzhh3ifqs010jz26q2jlh-mrjam-protected-admission-controller-1'
CTL='/nix/store/0xiinbh7pbj479i5v28mqnjrvhvbdibf-systemd-260.2/bin/systemctl'
PROFILE='/nix/var/nix/profiles/system'
JOURNAL=Path('/var/lib/mrjam-delivery-captures/preparation-anchor-activation-001.json')
UNITS=['nginx.service','postgresql.service','forgejo.service','mrjam-rust-blue.service','mrjam-rust-green.service','mrjam-forgejo-runner.service']
def require(ok,code):
    if not ok:raise RuntimeError(code)
def run(args):
    p=subprocess.run(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=180)
    require(p.returncode==0 and len(p.stdout)<=65536,'GUARD_COMMAND_REFUSED');return p.stdout
def retained():return {u:run([CTL,'show',u,'-p','MainPID','-p','ActiveState','-p','SubState']).decode() for u in UNITS}
def checkpoint(phase):
    temporary=JOURNAL.with_suffix('.next')
    fd=os.open(temporary,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as out:
        out.write(json.dumps({'phase':phase,'old':OLD,'old_boot':BOOT,'new':NEW}).encode());out.flush();os.fsync(out.fileno())
    os.replace(temporary,JOURNAL)
    fd=os.open(JOURNAL.parent,os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)
def runner():
    pid=int(run([CTL,'show','mrjam-forgejo-runner.service','-p','MainPID','--value']))
    root=Path('/proc')/str(pid)/'root'
    for name in ['etc/mrjam-forgejo-runner/admission.json','var/lib/mrjam-validation-admissions','run/mrjam-validation-authority/request.sock']:
        a=(Path('/')/name).stat();b=(root/name).stat()
        require((a.st_dev,a.st_ino)==(b.st_dev,b.st_ino) and b.st_nlink>0,'GUARD_RUNNER_MOUNT_CHANGED')
def main():
    require(os.getuid()==0 and len(sys.argv)==1 and os.uname().nodename=='srv1982677','GUARD_HOST_REFUSED')
    with open('/var/lib/mrjam-cutover/first-deployment/transaction.lock','rb') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        require(os.path.realpath('/run/current-system')==OLD and os.path.realpath(PROFILE)==BOOT and not JOURNAL.exists(),'GUARD_BASELINE_REFUSED')
        require(not Path('/var/lib/mrjam-staging/lease.json').exists(),'STAGING_EXISTING_LEASE_REFUSED')
        for count,directory in enumerate(Path('/var/lib/mrjam-intake-admission/jobs').iterdir(),1):
            require(count<=64 and re.fullmatch('[0-9a-f]{64}',directory.name),'STAGING_JOB_INVENTORY_REFUSED')
            value=json.loads((directory/'state.json').read_bytes())
            require((value['phase'] in {'deployed','failed','obsolete'} or (directory.name=='68f75aceaf25b4dc11bd8ab10fe06ce01fb23f6c93cc988b6b1d316ab25f9b75' and value['phase']=='validated' and value['capture']['proposal_sha256']=='6135a1bda1eb637fb17c445c28b686f8d97f1acca5151f28ea73bc073d78657f')) and value.get('promotion') is None,'STAGING_JOB_IN_FLIGHT')
        before=retained();require(all('ActiveState=active\n' in v for v in before.values()),'GUARD_RETAINED_INACTIVE')
        nginx=Path('/etc/nginx/nginx.conf').read_bytes();adopted=Path('/etc/mrjam-delivery-adopted.json').read_bytes()
        require(Path(NEW+'/etc/nginx/nginx.conf').read_bytes()==nginx,'GUARD_ROUTE_CHANGED')
        require('ExecStart='+PREPARER+'\n' in Path(NEW+'/etc/systemd/system/mrjam-delivery-preparation.service').read_text(),'PREPARATION_PACKAGE_REFUSED')
        checkpoint('prepared');boot_changed=False
        try:
            for phase,target in [('first-guard',NEW),('real-return',OLD),('final-guard',NEW)]:
                checkpoint(phase);run([target+'/bin/switch-to-configuration','test'])
                require(os.path.realpath('/run/current-system')==target and retained()==before,'GUARD_PROCESS_CHANGED')
                require(Path('/etc/nginx/nginx.conf').read_bytes()==nginx and Path('/etc/mrjam-delivery-adopted.json').read_bytes()==adopted,'GUARD_CONFIGURATION_CHANGED')
                runner()
                if target==NEW:
                    require(PACKAGE+'/bin/mrjam-admission-controller' in Path('/etc/systemd/system/mrjam-admission-controller.service').read_text(),'GUARD_PACKAGE_REFUSED')
            boot_changed=True
            run(['/run/current-system/sw/bin/nix-env','--profile',PROFILE,'--set',NEW]);run([NEW+'/bin/switch-to-configuration','boot'])
            require(os.path.realpath(PROFILE)==NEW and retained()==before,'GUARD_BOOT_REFUSED');runner()
            checkpoint('staging-active-and-boot')
        except Exception:
            restored=False
            try:
                run([OLD+'/bin/switch-to-configuration','test'])
                if boot_changed:
                    run(['/run/current-system/sw/bin/nix-env','--profile',PROFILE,'--set',BOOT]);run([BOOT+'/bin/switch-to-configuration','boot'])
                restored=os.path.realpath('/run/current-system')==OLD and os.path.realpath(PROFILE)==BOOT and retained()==before
            except Exception:pass
            checkpoint('returned-after-failure' if restored else 'recovery-required')
            print(json.dumps({'code':'GUARD_ACTIVATION_FAILED','previous_restored':restored}));raise SystemExit(2)
    require('ExecStart='+PREPARER+'\n' in Path('/etc/systemd/system/mrjam-delivery-preparation.service').read_text(),'PREPARATION_PACKAGE_REFUSED')
    require(run([CTL,'is-active','mrjam-delivery-preparation.timer']).strip()==b'active','PREPARATION_TIMER_INACTIVE')
    require(retained()==before,'GUARD_PROCESS_CHANGED')
    print(json.dumps({'code':'PREPARATION_ANCHOR_REPLACED','current':NEW,'boot':NEW,
        'real_return_verified':True,'retained_processes_unchanged':True,'new_delivery_promoted':False}))
if __name__=='__main__':
    try:main()
    except Exception as error:
        code=str(error) if type(error) is RuntimeError and re.fullmatch('[A-Z_]{1,80}',str(error)) else 'GUARD_ACTIVATION_REFUSED'
        print(json.dumps({'code':code,'exception_type':type(error).__name__}));raise SystemExit(2) from None
