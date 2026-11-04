"""Install dormant durable recovery service; no delivery plan is created."""
import fcntl,json,os,re,stat,subprocess,sys
from pathlib import Path
OLD='/nix/store/wjx28fxryilx9hq6szckhqn871jbf4zb-nixos-system-srv1982677-26.05pre-git'
BOOT=OLD
NEW='/nix/store/xs2q4rwk8bhr78y7l1xqkzl60244312k-nixos-system-srv1982677-26.05pre-git'
PACKAGE='/nix/store/qmzbv6zskr9qzhh3ifqs010jz26q2jlh-mrjam-protected-admission-controller-1'
CTL='/nix/store/0xiinbh7pbj479i5v28mqnjrvhvbdibf-systemd-260.2/bin/systemctl'
PROFILE='/nix/var/nix/profiles/system'
JOURNAL=Path('/var/lib/mrjam-delivery-captures/promotion-runtime-activation-001.json')
UNITS=['nginx.service','postgresql.service','forgejo.service','vise.service','mrjam-rust-blue.service','mrjam-rust-green.service','mrjam-forgejo-runner.service']
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
        require(not Path('/var/lib/mrjam-promotion/plan.json').exists(),'RECOVERY_PLAN_ALREADY_EXISTS')
        before=retained();require(all('ActiveState=active\n' in v for v in before.values()),'GUARD_RETAINED_INACTIVE')
        nginx=Path('/etc/nginx/nginx.conf').read_bytes();adopted=Path('/etc/mrjam-delivery-adopted.json').read_bytes()
        require(Path(NEW+'/etc/nginx/nginx.conf').read_bytes()==nginx,'GUARD_ROUTE_CHANGED')
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
            checkpoint('guard-active-and-boot')
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
    run([CTL,'start','mrjam-admission-controller.service'])
    require(run([CTL,'show','mrjam-admission-controller.service','-p','Result','--value']).strip()==b'success','GUARD_CONTROLLER_FAILED')
    unit=Path('/etc/systemd/system/mrjam-promotion.service').read_text()
    require('ConditionPathExists=/var/lib/mrjam-promotion/plan.json' in unit and '/nix/store/1aj8c8s3q34dj5cf7x7gcw1grbk36im8-mrjam-protected-promotion-service-1/bin/mrjam-promotion' in unit,'RECOVERY_SERVICE_REFUSED')
    run([CTL,'start','mrjam-promotion.service'])
    require(run([CTL,'show','mrjam-promotion.service','-p','ConditionResult','--value']).strip()==b'no','RECOVERY_MUST_REMAIN_DORMANT')
    require(run([CTL,'is-active','mrjam-promotion.timer']).strip()==b'active','RECOVERY_TIMER_INACTIVE')
    print(json.dumps({'code':'PROMOTION_RUNTIME_ACTIVE','current':NEW,'boot':NEW,'real_return_verified':True,'retained_processes_unchanged':True,'new_delivery_promoted':False}))
if __name__=='__main__':
    try:main()
    except Exception as error:
        code=str(error) if type(error) is RuntimeError and re.fullmatch('[A-Z_]{1,80}',str(error)) else 'GUARD_ACTIVATION_REFUSED'
        print(json.dumps({'code':code,'exception_type':type(error).__name__}));raise SystemExit(2) from None
