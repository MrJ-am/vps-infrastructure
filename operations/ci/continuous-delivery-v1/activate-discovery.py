"""One fixed administrative activation: read-only discovery, no application release."""
import fcntl,json,os,stat,subprocess,time
from pathlib import Path
OLD='/nix/store/17lw8y05pgzmcl9q6wvknbf7z1znajl9-nixos-system-srv1982677-26.05pre-git'
NEW='/nix/store/q7s20jjy4b0czv3kj1kmzi15r7inr94f-nixos-system-srv1982677-26.05pre-git'
SYSTEMD='/nix/store/0xiinbh7pbj479i5v28mqnjrvhvbdibf-systemd-260.2/bin/systemctl'
NIX_ENV='/run/current-system/sw/bin/nix-env'
PROFILE='/nix/var/nix/profiles/system'
UNITS=['postgresql.service','nginx.service','forgejo.service','vise.service','mrjam-rust-blue.service','mrjam-rust-green.service']
def require(value,code):
    if not value:raise RuntimeError(code)
def run(argv,timeout=180):
    result=subprocess.run(argv,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=timeout)
    require(result.returncode==0,'COMMAND_FAILED')
def properties(unit):
    result=subprocess.run([SYSTEMD,'show',unit,'-p','ActiveState','-p','SubState','-p','MainPID'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=10,check=True)
    return dict(line.split('=',1) for line in result.stdout.decode().splitlines() if '=' in line)
def baseline():return {name:properties(name) for name in UNITS}
def main():
    require(os.getuid()==0,'ADMIN_REQUIRED')
    lock=os.open('/run/mrjam-discovery-activation.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    require(os.path.realpath('/run/current-system')==OLD and os.path.realpath(PROFILE)==OLD,'BASELINE_CHANGED')
    require(Path(NEW+'/bin/switch-to-configuration').is_file(),'CANDIDATE_ABSENT')
    before=baseline()
    require(all(before[n]['ActiveState']=='active' for n in UNITS if n!='mrjam-rust-green.service'),'RETAINED_SERVICE_NOT_ACTIVE')
    started=int(time.time());promoted=False
    try:
        run([NEW+'/bin/switch-to-configuration','test'])
        require(os.path.realpath('/run/current-system')==NEW,'CURRENT_SYSTEM_REFUSED')
        require(baseline()==before,'RETAINED_PROCESS_CHANGED')
        require(properties('mrjam-github-discovery.timer')['ActiveState']=='active','TIMER_INACTIVE')
        run([SYSTEMD,'start','mrjam-github-discovery.service'])
        snapshot=Path('/var/lib/mrjam-github-discovery/proposals.json')
        value=json.loads(snapshot.read_bytes())
        require(value['scope']=='discovery-only-no-admission' and value['read_token_revoked'] is True
            and value['deployment_authorized'] is False and value['observed_at']>=started,'FRESH_DISCOVERY_REQUIRED')
        require(baseline()==before,'RETAINED_PROCESS_CHANGED')
        run([NIX_ENV,'--profile',PROFILE,'--set',NEW]);promoted=True
        run([NEW+'/bin/switch-to-configuration','boot'])
        require(os.path.realpath(PROFILE)==NEW and os.path.realpath('/run/current-system')==NEW,'BOOT_PROFILE_REFUSED')
        key=Path('/var/lib/mrjam-github-app/app-credentials.json').stat()
        require(key.st_uid==0 and stat.S_IMODE(key.st_mode)==0o400,'APP_CREDENTIAL_CHANGED')
        print(json.dumps({'code':'DISCOVERY_ACTIVE_AND_BOOT','current':NEW,'boot':os.path.realpath(PROFILE),
            'retained_processes_unchanged':True,'discovery_timer':properties('mrjam-github-discovery.timer'),
            'proposals':len(value['proposals']),'ignored':len(value['ignored']),'read_token_revoked':True,
            'app_private_key_root_0400':True,'automatic_deployment_enabled':False},sort_keys=True))
    except Exception:
        try:
            if promoted:run([NIX_ENV,'--profile',PROFILE,'--set',OLD])
            run([OLD+'/bin/switch-to-configuration','switch'])
            restored=os.path.realpath('/run/current-system')==OLD and os.path.realpath(PROFILE)==OLD
        except Exception:restored=False
        print(json.dumps({'code':'DISCOVERY_ACTIVATION_FAILED','configuration_return_verified':restored}))
        raise SystemExit(1) from None
    finally:os.close(lock)
if __name__=='__main__':
    try:main()
    except Exception:
        print('{"code":"DISCOVERY_PREFLIGHT_REFUSED"}');raise SystemExit(1) from None
