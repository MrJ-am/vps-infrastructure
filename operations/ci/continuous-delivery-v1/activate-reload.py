"""Fixed one-time Nginx configuration-path transition, with configuration return."""
import fcntl
import http.client
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import time

OLD='/nix/store/q7s20jjy4b0czv3kj1kmzi15r7inr94f-nixos-system-srv1982677-26.05pre-git'
NEW='/nix/store/xqbbs66wf4q9n7fdrs9p54bf87ak264a-nixos-system-srv1982677-26.05pre-git'
CTL='/nix/store/0xiinbh7pbj479i5v28mqnjrvhvbdibf-systemd-260.2/bin/systemctl'
PROFILE='/nix/var/nix/profiles/system'
UNITS=['postgresql.service','forgejo.service','vise.service','mrjam-rust-blue.service','mrjam-rust-green.service']
HOSTS=['log.mrj.am','audition.mrj.am','vision.mrj.am','forge.mrj.am','vise.mrj.am']

def require(value,code):
    if not value:raise RuntimeError(code)

def run(args,timeout=180):
    result=subprocess.run(args,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL,timeout=timeout)
    require(result.returncode==0,'COMMAND_FAILED')

def properties(unit):
    result=subprocess.run([CTL,'show',unit,'-p','ActiveState','-p','SubState','-p','MainPID'],
                          stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=10,check=True)
    return dict(line.split('=',1) for line in result.stdout.decode().splitlines())

def retained():return {unit:properties(unit) for unit in UNITS}

def probe():
    result={}
    context=ssl.create_default_context(cafile='/etc/ssl/certs/ca-certificates.crt')
    for host in HOSTS:
        # Validate the public certificate/name, but address only the local VPS.
        connection=http.client.HTTPSConnection(host,timeout=10,context=context)
        try:
            connection.sock=context.wrap_socket(socket.create_connection(('127.0.0.1',443),10),server_hostname=host)
            connection.request('GET','/',headers={'Connection':'close'})
            response=connection.getresponse()
            require(200<=response.status<500,'HTTPS_SERVICE_FAILED')
            result[host]=response.status
        finally:connection.close()
    return result

def ready(expected):
    # systemd Type=simple may report active before Nginx binds its TLS socket.
    for attempt in range(20):
        try:
            if probe()==expected:return True
        except (OSError,http.client.HTTPException,RuntimeError):pass
        time.sleep(.5)
    return False

def main():
    require(os.getuid()==0,'ADMIN_REQUIRED')
    lock=os.open('/run/mrjam-reload-activation.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    require(os.path.realpath('/run/current-system')==OLD and os.path.realpath(PROFILE)==OLD,'BASELINE_CHANGED')
    require(Path(NEW+'/bin/switch-to-configuration').is_file(),'CANDIDATE_ABSENT')
    before=retained()
    require(all(before[n]['ActiveState']=='active' for n in UNITS if n!='mrjam-rust-green.service'),'RETAINED_SERVICE_NOT_ACTIVE')
    nginx_before=properties('nginx.service')
    require(nginx_before['ActiveState']=='active','NGINX_NOT_ACTIVE')
    executable=os.path.realpath('/proc/'+nginx_before['MainPID']+'/exe')
    require(executable.startswith('/nix/store/') and executable.endswith('/bin/nginx'),'NGINX_EXECUTABLE_REFUSED')
    status_before=probe()
    changed=False
    stage='switch-test'
    try:
        changed=True
        run([NEW+'/bin/switch-to-configuration','test'])
        require(os.path.realpath('/run/current-system')==NEW,'CURRENT_SYSTEM_REFUSED')
        require(retained()==before,'RETAINED_PROCESS_CHANGED')
        stage='nginx-config-test'
        run([executable,'-t','-c','/etc/nginx/nginx.conf'])
        stage='nginx-restart'
        run([CTL,'restart','nginx.service'])
        require(ready(status_before),'HTTPS_READINESS_FAILED')
        nginx_after=properties('nginx.service')
        require(nginx_after['ActiveState']=='active' and nginx_after['MainPID']!=nginx_before['MainPID'],'NEW_MASTER_REQUIRED')
        command=Path('/proc/'+nginx_after['MainPID']+'/cmdline').read_bytes()
        require(b'/etc/nginx/nginx.conf' in command,'STABLE_CONFIGURATION_PATH_REQUIRED')
        require(probe()==status_before and retained()==before,'SERVICE_CONTINUITY_CHECK_FAILED')
        stage='graceful-reload'
        run([CTL,'reload','nginx.service'])
        require(properties('nginx.service')==nginx_after and probe()==status_before,'GRACEFUL_RELOAD_FAILED')
        stage='boot-profile'
        run(['/run/current-system/sw/bin/nix-env','--profile',PROFILE,'--set',NEW])
        run([NEW+'/bin/switch-to-configuration','boot'])
        require(os.path.realpath(PROFILE)==NEW and os.path.realpath('/run/current-system')==NEW,'BOOT_PROFILE_REFUSED')
        require(retained()==before,'RETAINED_PROCESS_CHANGED')
        print(json.dumps({'code':'NATIVE_RELOAD_ACTIVE_AND_BOOT','current':NEW,'boot':NEW,
                          'retained_processes_unchanged':True,'initial_nginx_restart':True,
                          'subsequent_reload_preserved_master':True,'https_statuses':status_before,
                          'automatic_deployment_enabled':False},sort_keys=True))
    except Exception as failure:
        code=str(failure) if isinstance(failure,RuntimeError) else type(failure).__name__
        restored=False
        if changed:
            try:
                run(['/run/current-system/sw/bin/nix-env','--profile',PROFILE,'--set',OLD])
                run([OLD+'/bin/switch-to-configuration','switch'])
                run([CTL,'restart','nginx.service'])
                restored=os.path.realpath('/run/current-system')==OLD and os.path.realpath(PROFILE)==OLD and ready(status_before)
            except Exception:pass
        print(json.dumps({'code':'NATIVE_RELOAD_ACTIVATION_FAILED','stage':stage,'failure':code,'configuration_return_verified':restored}))
        raise SystemExit(1) from None
    finally:os.close(lock)

if __name__=='__main__':
    try:main()
    except Exception:
        print('{"code":"NATIVE_RELOAD_PREFLIGHT_REFUSED"}');raise SystemExit(1) from None
