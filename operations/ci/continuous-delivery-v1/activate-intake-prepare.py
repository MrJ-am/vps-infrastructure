"""Activate only source preparation, verify real return, retain applications."""
import fcntl,json,os,sqlite3,subprocess
from pathlib import Path
OLD='/nix/store/6h7c3bvc9969v2qvlxcjyjrp7cxzsq2h-nixos-system-srv1982677-26.05pre-git'
NEW='/nix/store/qjkig4qypn3640v2i9gb1qi4w0r48hj6-nixos-system-srv1982677-26.05pre-git'
PACKAGE='/nix/store/vs5dc3klynsc1xm83sm9l55s4aqrz60f-mrjam-exact-intake-preparation-1'
CTL='/nix/store/0xiinbh7pbj479i5v28mqnjrvhvbdibf-systemd-260.2/bin/systemctl'
PROFILE='/nix/var/nix/profiles/system'
STATE=Path('/var/lib/private/mrjam-github-discovery')
JOURNAL=Path('/var/lib/mrjam-delivery-captures/intake-preparation-activation-001.json')
UNITS=['nginx.service','postgresql.service','forgejo.service','vise.service','mrjam-rust-blue.service','mrjam-rust-green.service','mrjam-forgejo-runner.service']
def require(ok,code):
    if not ok:raise RuntimeError(code)
def run(args,capture=False):
    p=subprocess.run(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,timeout=870)
    require(p.returncode==0,'PREPARATION_COMMAND_FAILED')
    if capture:require(len(p.stdout)<=65536,'OUTPUT_LIMIT');return p.stdout
def retained():return {u:run([CTL,'show',u,'-p','MainPID','-p','ActiveState','-p','SubState'],True).decode() for u in UNITS}
def checkpoint(phase):
    tmp=JOURNAL.with_suffix('.next')
    fd=os.open(tmp,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as f:
        f.write(json.dumps({'phase':phase,'previous':OLD,'new':NEW}).encode());f.flush();os.fsync(f.fileno())
    os.replace(tmp,JOURNAL)
    fd=os.open(JOURNAL.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)
def prepare():
    unit=Path('/etc/systemd/system/mrjam-intake-prepare.service').read_text()
    require(PACKAGE+'/bin/mrjam-intake-prepare' in unit,'PREPARATION_EXECUTABLE_REFUSED')
    require('TemporaryFileSystem=/tmp:rw,size=512M,mode=1777' in unit,'PREPARATION_BOUND_REFUSED')
    run([CTL,'start','mrjam-intake-prepare.service'])
    require(run([CTL,'show','mrjam-intake-prepare.service','-p','Result','--value'],True).strip()==b'success','PREPARATION_UNIT_FAILED')
    db=sqlite3.connect('file:'+str(STATE/'intake.sqlite')+'?mode=ro',uri=True)
    try:
        states={r[0]:r[1] for r in db.execute('SELECT state,count(*) FROM jobs GROUP BY state')}
        require('running' not in states,'PREPARATION_LEFT_RUNNING')
    finally:db.close()
    require(run([CTL,'is-active','mrjam-intake-prepare.timer'],True).strip()==b'active','PREPARATION_TIMER_INACTIVE')
    return states
def main():
    require(os.getuid()==0 and os.uname().nodename=='srv1982677','HOST_REFUSED')
    lock=os.open('/var/lib/mrjam-cutover/first-deployment/transaction.lock',os.O_RDWR|os.O_NOFOLLOW)
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    require(os.path.realpath('/run/current-system')==OLD and os.path.realpath(PROFILE)==OLD and not JOURNAL.exists(),'BASELINE_CHANGED')
    before=retained();require(all('ActiveState=active\n' in x for x in before.values()),'RETAINED_SERVICE_INACTIVE')
    checkpoint('prepared');boot_changed=False
    try:
        states=[]
        for phase,target in [('first-preparation',NEW),('real-return',OLD),('final-preparation',NEW)]:
            checkpoint(phase);run([target+'/bin/switch-to-configuration','test'])
            require(retained()==before and os.path.realpath('/run/current-system')==target,'RETAINED_STATE_CHANGED')
            if target==NEW:states.append(prepare())
        boot_changed=True
        run(['/run/current-system/sw/bin/nix-env','--profile',PROFILE,'--set',NEW])
        run([NEW+'/bin/switch-to-configuration','boot'])
        require(retained()==before and os.path.realpath(PROFILE)==NEW and os.path.realpath('/run/current-system')==NEW,'BOOT_STATE_REFUSED')
        checkpoint('source-preparation-active-and-boot')
        print(json.dumps({'code':'SOURCE_PREPARATION_ACTIVE','current':NEW,'boot':NEW,'queue_states':states,
            'real_return_verified':True,'retained_processes_unchanged':True,'new_admission_performed':False,'automatic_deployment_enabled':False}))
    except Exception as error:
        restored=False
        try:
            run([OLD+'/bin/switch-to-configuration','test'])
            if boot_changed:
                run(['/run/current-system/sw/bin/nix-env','--profile',PROFILE,'--set',OLD])
                run([OLD+'/bin/switch-to-configuration','boot'])
            restored=retained()==before and os.path.realpath('/run/current-system')==OLD and os.path.realpath(PROFILE)==OLD
            checkpoint('returned-after-failure' if restored else 'recovery-required')
        except Exception:pass
        print(json.dumps({'code':'PREPARATION_ACTIVATION_FAILED','cause':str(error) if isinstance(error,RuntimeError) else type(error).__name__,
            'previous_restored':restored}));raise SystemExit(2)
    finally:os.close(lock)
if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps({'code':str(error) if isinstance(error,RuntimeError) else 'PREPARATION_PREFLIGHT_FAILED'}));raise SystemExit(2)
