"""Install only persistent read-only discovery; test real return and boot."""
import fcntl,json,os,sqlite3,stat,subprocess,time
from pathlib import Path
OLD='/nix/store/xrh880q8hiv7c4v7cng5mi1vg4j6p264-nixos-system-srv1982677-26.05pre-git'
NEW='/nix/store/6h7c3bvc9969v2qvlxcjyjrp7cxzsq2h-nixos-system-srv1982677-26.05pre-git'
PACKAGE='/nix/store/pp91fpraqdkassx2v09qvx4kqj00pk76-mrjam-persistent-intake-discovery-1'
CTL='/nix/store/0xiinbh7pbj479i5v28mqnjrvhvbdibf-systemd-260.2/bin/systemctl'
PROFILE='/nix/var/nix/profiles/system'
STATE=Path('/var/lib/private/mrjam-github-discovery')
JOURNAL=Path('/var/lib/mrjam-delivery-captures/intake-activation-001.json')
UNITS=['nginx.service','postgresql.service','forgejo.service','vise.service','mrjam-rust-blue.service','mrjam-rust-green.service','mrjam-forgejo-runner.service']
def require(ok,code):
    if not ok:raise RuntimeError(code)
def run(args,capture=False):
    p=subprocess.run(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE if capture else subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=210)
    require(p.returncode==0,'INTAKE_COMMAND_FAILED')
    if capture:require(len(p.stdout)<=65536,'OUTPUT_LIMIT');return p.stdout
def retained():return {u:run([CTL,'show',u,'-p','MainPID','-p','ActiveState','-p','SubState'],True).decode() for u in UNITS}
def checkpoint(phase):
    tmp=JOURNAL.with_suffix('.next')
    fd=os.open(tmp,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as f:f.write(json.dumps({'phase':phase,'previous':OLD,'new':NEW}).encode());f.flush();os.fsync(f.fileno())
    os.replace(tmp,JOURNAL)
    fd=os.open(JOURNAL.parent,os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)
def discover():
    require(PACKAGE+'/bin/mrjam-github-discover' in Path('/etc/systemd/system/mrjam-github-discovery.service').read_text(),'DISCOVERY_EXECUTABLE_REFUSED')
    started=int(time.time());run([CTL,'start','mrjam-github-discovery.service'])
    snapshot=json.loads((STATE/'proposals.json').read_bytes())
    require(snapshot['observed_at']>=started and snapshot['read_token_revoked'] and snapshot['deployment_authorized'] is False,'FRESH_DISCOVERY_REQUIRED')
    info=(STATE/'intake.sqlite').lstat();require(stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode)==0o600,'QUEUE_METADATA_REFUSED')
    db=sqlite3.connect('file:'+str(STATE/'intake.sqlite')+'?mode=ro',uri=True)
    try:
        require(db.execute('PRAGMA user_version').fetchone()[0]==1,'QUEUE_SCHEMA_REFUSED')
        count=db.execute('SELECT count(*) FROM jobs WHERE visible=1').fetchone()[0]
        require(count==len(snapshot['proposals']),'QUEUE_OBSERVATION_MISMATCH')
    finally:db.close()
    require(run([CTL,'is-active','mrjam-github-discovery.timer'],True).strip()==b'active','DISCOVERY_TIMER_INACTIVE')
    return count
def main():
    require(os.getuid()==0 and os.uname().nodename=='srv1982677','HOST_REFUSED')
    lock=os.open('/var/lib/mrjam-cutover/first-deployment/transaction.lock',os.O_RDWR|os.O_NOFOLLOW);fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    require(os.path.realpath('/run/current-system')==OLD and os.path.realpath(PROFILE)==OLD and not JOURNAL.exists(),'BASELINE_CHANGED')
    before=retained();require(all('ActiveState=active\n' in x for x in before.values()),'RETAINED_SERVICE_INACTIVE')
    checkpoint('prepared');boot_changed=False
    try:
        counts=[]
        for phase,target in [('first-intake',NEW),('real-return',OLD),('final-intake',NEW)]:
            checkpoint(phase);run([target+'/bin/switch-to-configuration','test'])
            require(retained()==before and os.path.realpath('/run/current-system')==target,'RETAINED_STATE_CHANGED')
            if target==NEW:counts.append(discover())
        boot_changed=True
        run(['/run/current-system/sw/bin/nix-env','--profile',PROFILE,'--set',NEW]);run([NEW+'/bin/switch-to-configuration','boot'])
        require(retained()==before and os.path.realpath(PROFILE)==NEW and os.path.realpath('/run/current-system')==NEW,'BOOT_STATE_REFUSED')
        checkpoint('persistent-discovery-active-and-boot')
        print(json.dumps({'code':'PERSISTENT_INTAKE_DISCOVERY_ACTIVE','current':NEW,'boot':NEW,'queue_counts':counts,
            'real_return_verified':True,'retained_processes_unchanged':True,'new_admission_performed':False,'automatic_deployment_enabled':False}))
    except Exception as error:
        restored=False
        try:
            run([OLD+'/bin/switch-to-configuration','test'])
            if boot_changed:
                run(['/run/current-system/sw/bin/nix-env','--profile',PROFILE,'--set',OLD]);run([OLD+'/bin/switch-to-configuration','boot'])
            restored=retained()==before and os.path.realpath('/run/current-system')==OLD and os.path.realpath(PROFILE)==OLD
            checkpoint('returned-after-failure' if restored else 'recovery-required')
        except Exception:pass
        print(json.dumps({'code':'INTAKE_ACTIVATION_FAILED','cause':str(error) if isinstance(error,RuntimeError) else type(error).__name__,'previous_restored':restored}));raise SystemExit(2)
    finally:os.close(lock)
if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps({'code':str(error) if isinstance(error,RuntimeError) else 'INTAKE_PREFLIGHT_FAILED'}));raise SystemExit(2)
