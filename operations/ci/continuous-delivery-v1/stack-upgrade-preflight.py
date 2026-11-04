"""Fixed read-only upgrade preflight; no credentials, application data or logs."""
import fcntl,json,os,re,stat,subprocess,sys
from pathlib import Path
sys.path[:0]=[
 '/nix/store/5zapz1574xm5whrqsw28c0j0mjjc6pzh-mrjam-protected-staging-service-1/lib',
 '/nix/store/zkp2pvjhibqr0i68062ngfaskyrbcawx-mrjam-separated-acceptance-services-1/lib',
 '/nix/store/ffsi1j9zw9b571p7cp2a39p27sbijsr9-mrjam-protected-admission-controller-1/lib',
 '/nix/store/cn315ryfbdp3swn5dm7npk35yvmfsx65-mrjam-validation-admission-control-1/lib']
import admission_orchestrator as O
import delivery_environment as E
import staging_lease as L

def main():
    assert os.geteuid()==0 and os.uname().nodename=='srv1982677' and len(sys.argv)==1
    fd=os.open('/var/lib/mrjam-cutover/first-deployment/transaction.lock',os.O_RDONLY|os.O_NOFOLLOW)
    try:
        info=os.fstat(fd)
        assert stat.S_ISREG(info.st_mode) and info.st_uid==0 and info.st_nlink==1
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            print('{"code":"STACK_UPGRADE_ENVIRONMENT_BUSY"}');return
        state=E.read()
        jobs=Path('/var/lib/mrjam-intake-admission/jobs');counts={};promotions=0
        for count,path in enumerate(jobs.iterdir(),1):
            assert count<=O.MAX_JOBS and re.fullmatch('[0-9a-f]{64}',path.name)
            O.W.private_directory(path);job=O.read(path/'state.json')
            phase=job['phase'];counts[phase]=counts.get(phase,0)+1
            promotions+=job.get('promotion') is not None
        lease=Path('/var/lib/mrjam-staging/lease.json')
        pending=L.pending_commit(Path('/var/lib/mrjam-acceptance'),jobs) is not None
        patterns=['mrjam-validation-worker@*.service','mrjam-validation-collector@*.service',
            'mrjam-validation-export@*.service','mrjam-validation-authority.service']
        raw=subprocess.check_output(['systemctl','list-units','--state=active,activating,deactivating',
            '--type=service','--output=json',*patterns],timeout=10)
        assert len(raw)<=65536
        busy=json.loads(raw);assert type(busy) is list
        stable=state['system']=='/nix/store/04j3v1y76rx8l762zp5dc4059wfcnhhw-nixos-system-srv1982677-26.05pre-git'
        eligible=stable and set(counts)<={'deployed','failed','obsolete'} and promotions==0 \
            and not (lease.exists() or lease.is_symlink() or pending or busy)
        print(json.dumps({'schema_version':1,'code':'STACK_UPGRADE_PREFLIGHT',
            'baseline_exact':stable,'job_phases':counts,'promotion_markers':promotions,
            'staging_lease_present':lease.exists() or lease.is_symlink(),'pending_acceptance':pending,
            'active_validation_units':len(busy),'eligible_at_observation':eligible,
            'system':state['system'],'production_mutation':False},sort_keys=True))
    finally:os.close(fd)

if __name__=='__main__':
    try:main()
    except Exception as error:
        code=str(error) if re.fullmatch('[A-Z_]{1,80}',str(error)) else 'STACK_PREFLIGHT_REFUSED'
        print(json.dumps({'code':code,'exception_type':type(error).__name__}));raise SystemExit(1)
