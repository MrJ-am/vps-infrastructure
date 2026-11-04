"""Bounded native Nix GC, preserving current/return roots and application state.

No profile generation, GC root, application path or backup is selected for
deletion. Nix chooses only unreferenced store objects, up to a 4 GiB target.
"""
import fcntl,json,os,re,stat,subprocess,sys,time
from pathlib import Path

NIX='/run/current-system/sw/bin/nix-store'
CTL='/run/current-system/sw/bin/systemctl'
CURRENT='/nix/store/9ng98pjns0pvrfmigg29i79rdqgxqdi2-nixos-system-srv1982677-26.05pre-git'
REQUIRED=[CURRENT,
 '/nix/store/04j3v1y76rx8l762zp5dc4059wfcnhhw-nixos-system-srv1982677-26.05pre-git',
 '/nix/store/cwrqy0vp5q1r7vzpj8p8fa5cd4650c7y-mrjam-protected-delivery-stack-1',
 '/nix/store/cn315ryfbdp3swn5dm7npk35yvmfsx65-mrjam-validation-admission-control-1',
 '/nix/store/74329d2w5p244s4rvpfip1c70cvb4qid-mrjam-vise-rules-independent-audit-1',
 '/nix/store/ifj6nyig0yvxsp024cgd8yylhxd4ql66-mrjam-vise-rules-audit-publisher-1',
 '/nix/store/zmb0mvkn59zxpxnc9ny02q4rkaffc5bw-mrjam-vise-0.2.0-8c8ef66f943c']
UNITS=['nginx.service','forgejo.service','postgresql.service','vise.service',
 'mrjam-rust-blue.service','mrjam-rust-green.service','mrjam-forgejo-runner.service']

def need(ok,code):
    if not ok:raise RuntimeError(code)

def run(args,timeout=90):
    p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
    need(p.returncode==0 and len(p.stdout)<=32*1024**2,'STORE_COMMAND_REFUSED')
    return p

def state():
    need(os.path.realpath('/run/current-system')==os.path.realpath('/nix/var/nix/profiles/system')==CURRENT,
        'STORE_GENERATION_CHANGED')
    result={}
    for unit in UNITS:
        value=run([CTL,'show',unit,'-p','ActiveState','-p','MainPID','-p','ActiveEnterTimestampMonotonic']).stdout.decode()
        need('ActiveState=active\n' in value,'STORE_SERVICE_INACTIVE');result[unit]=value
    return result

def free():
    value=os.statvfs('/nix/store');return value.f_bavail*value.f_frsize

def main():
    need(os.geteuid()==0 and len(sys.argv)==1 and os.uname().nodename=='srv1982677','STORE_HOST_REFUSED')
    with open('/var/lib/mrjam-cutover/first-deployment/transaction.lock','rb') as lock:
        info=os.fstat(lock.fileno());need(stat.S_ISREG(info.st_mode) and info.st_uid==0,'STORE_LOCK_REFUSED')
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        before=state();available=free()
        live=set(run([NIX,'--gc','--print-live']).stdout.decode().splitlines())
        need(set(REQUIRED)<=live,'STORE_REQUIRED_ROOT_MISSING')
        started=time.monotonic()
        result=run([NIX,'--gc','--max-freed',str(4*1024**3)],timeout=900)
        run([NIX,'--check-validity',*REQUIRED])
        need(state()==before,'STORE_SERVICE_STATE_CHANGED')
        summary=re.findall(rb'([0-9]+) store paths deleted, ([0-9.]+) MiB freed',result.stderr)
        print(json.dumps({'schema_version':1,'code':'UNREFERENCED_STORE_RECLAIMED',
            'before_available_bytes':available,'after_available_bytes':free(),
            'seconds':round(time.monotonic()-started,3),'required_roots_verified':len(REQUIRED),
            'preserved_services':len(UNITS),'profile_generations_deleted':False,
            'backup_or_application_paths_deleted':False,
            'nix_summary':None if not summary else {'paths':int(summary[-1][0]),'mib':float(summary[-1][1])}},sort_keys=True))

if __name__=='__main__':
    try:main()
    except Exception as error:
        code=str(error) if type(error) is RuntimeError and re.fullmatch('[A-Z_]{1,80}',str(error)) else 'STORE_RECLAIM_REFUSED'
        print(json.dumps({'code':code}));raise SystemExit(1)
