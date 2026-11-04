"""One fixed control upgrade, real return and boot commit. No application deploy.

Shared lock and runtime inhibitors keep delivery writers quiescent. An abrupt
controller exit leaves inhibitors in place for explicit recovery. No token,
application database, backup contents or candidate-selected command is used.
"""
import fcntl,http.client,importlib.util,json,os,re,socket,ssl,stat,subprocess,sys,time
from pathlib import Path

OLD='/nix/store/04j3v1y76rx8l762zp5dc4059wfcnhhw-nixos-system-srv1982677-26.05pre-git'
NEW='/nix/store/9ng98pjns0pvrfmigg29i79rdqgxqdi2-nixos-system-srv1982677-26.05pre-git'
VIEW='/nix/store/hh6j0jmqf2r8immjpw1rg8si8c6d5p77-delivery-stack-export-evaluation-003.json'
RECIPE='/nix/store/rapjcp0v88hh05y7gy1fgck8p05fj6dn-mrjam-protected-delivery-recipe-1'
CTL='/nix/store/0xiinbh7pbj479i5v28mqnjrvhvbdibf-systemd-260.2/bin/systemctl'
PROFILE='/nix/var/nix/profiles/system'
RUNNER='mrjam-forgejo-runner.service'
WRITERS=['mrjam-admission-controller.service','mrjam-delivery-preparation.service',
    'mrjam-delivery-staging.service','mrjam-promotion.service']+[
    'mrjam-acceptance-'+stage+'.service' for stage in ('mirror','review','merge','sync')]
RETAINED=['nginx.service','postgresql.service','forgejo.service','vise.service',
    'mrjam-rust-blue.service','mrjam-rust-green.service','mrjam-identity.service',
    'mrjam-identity-deletion.service','mrjam-vision-admission.service','mrjam-vision-closure.service']
STATE=Path('/var/lib/mrjam-stack-upgrade-001')
PERMIT=Path('/run/mrjam-stack-upgrade-permit')
CONTENTS='[Unit]\nConditionPathExists='+str(PERMIT)+'\n'
RECOVERY=Path('/run/systemd/system/forgejo.service.wants/mrjam-forgejo-runner.service')
INITIAL={}

sys.path[:0]=[RECIPE+'/operations/ci/continuous-delivery-v1',
 '/nix/store/5zapz1574xm5whrqsw28c0j0mjjc6pzh-mrjam-protected-staging-service-1/lib',
 '/nix/store/zkp2pvjhibqr0i68062ngfaskyrbcawx-mrjam-separated-acceptance-services-1/lib',
 '/nix/store/ffsi1j9zw9b571p7cp2a39p27sbijsr9-mrjam-protected-admission-controller-1/lib',
 '/nix/store/cn315ryfbdp3swn5dm7npk35yvmfsx65-mrjam-validation-admission-control-1/lib']
import admission_orchestrator as O
import staging_lease as L

def need(value,code):
    if not value:raise RuntimeError(code)

def run(args,timeout=180):
    p=subprocess.run(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=timeout)
    need(p.returncode==0 and len(p.stdout)<=1048576,'STACK_COMMAND_REFUSED');return p.stdout

def properties(unit):
    raw=run([CTL,'show',unit,'-p','MainPID','-p','ActiveState','-p','SubState','-p','ActiveEnterTimestampMonotonic'])
    return dict(line.split('=',1) for line in raw.decode().splitlines())

def retained():return {u:properties(u) for u in RETAINED}

def probe():
    result={};context=ssl.create_default_context(cafile='/etc/ssl/certs/ca-certificates.crt')
    for host in ('log.mrj.am','audition.mrj.am','vision.mrj.am','forge.mrj.am','vise.mrj.am'):
        c=http.client.HTTPSConnection(host,timeout=10,context=context)
        try:
            c.sock=context.wrap_socket(socket.create_connection(('127.0.0.1',443),10),server_hostname=host)
            # ViSe's prototype dispatches methods explicitly: GET / is 200,
            # while HEAD / is 404. Observe normal public access; never read body.
            c.request('GET','/',headers={'Connection':'close'});response=c.getresponse()
            need(200<=response.status<400,'STACK_HTTPS_REFUSED');result[host]=response.status
        finally:c.close()
    return result

def idle():
    raw=run([CTL,'list-units','--state=active,activating,deactivating','--type=service','--output=json',
        'mrjam-validation-worker@*.service','mrjam-validation-collector@*.service',
        'mrjam-validation-export@*.service','mrjam-validation-authority.service'])
    need(json.loads(raw)==[],'STACK_VALIDATION_BUSY')
    jobs=Path('/var/lib/mrjam-intake-admission/jobs')
    for count,path in enumerate(jobs.iterdir(),1):
        need(count<=O.MAX_JOBS and re.fullmatch('[0-9a-f]{64}',path.name),'STACK_JOB_INVENTORY_REFUSED')
        O.W.private_directory(path);job=O.read(path/'state.json')
        need(job['phase'] in {'deployed','failed','obsolete'} and job.get('promotion') is None,'STACK_JOB_IN_FLIGHT')
    lease=Path('/var/lib/mrjam-staging/lease.json')
    need(not lease.exists() and not lease.is_symlink() and
        L.pending_commit(Path('/var/lib/mrjam-acceptance'),jobs) is None,'STACK_DELIVERY_PENDING')

def dropin(unit):return Path('/run/systemd/system',unit+'.d','95-mrjam-stack-upgrade.conf')

def inhibit(unit):
    path=dropin(unit);path.parent.mkdir(mode=0o755,exist_ok=True)
    if path.exists():need(not path.is_symlink() and path.read_text()==CONTENTS,'STACK_INHIBITOR_CHANGED')
    else:
        with path.open('x') as out:out.write(CONTENTS)

def release(unit):
    path=dropin(unit)
    need(not path.is_symlink() and path.read_text()==CONTENTS,'STACK_INHIBITOR_CHANGED')
    path.unlink()
    if not any(path.parent.iterdir()):path.parent.rmdir()

def checkpoint(phase,**extra):
    raw=json.dumps({'schema_version':1,'old':OLD,'new':NEW,'phase':phase,'initial':INITIAL,**extra},sort_keys=True).encode()
    path=STATE/'state.next';fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as out:out.write(raw);out.flush();os.fsync(out.fileno())
    os.replace(path,STATE/'state.json')
    fd=os.open(STATE,os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)

def runner(target):
    p=properties(RUNNER);need(p['ActiveState']=='active' and p['SubState']=='running','STACK_RUNNER_INACTIVE')
    pid=int(p['MainPID']);need(pid>0,'STACK_RUNNER_PID_REFUSED')
    unit=Path(target,'etc/systemd/system',RUNNER).read_text()
    command=re.findall(r'^ExecStart=(/nix/store/[^ ]+)/bin/forgejo-runner daemon --config %d/runner-config$',unit,re.M)
    root=re.findall(r'^RootDirectory=(/nix/store/[^\n]+)$',unit,re.M)
    need(len(command)==len(root)==1,'STACK_RUNNER_UNIT_REFUSED')
    need(os.path.realpath('/proc/'+str(pid)+'/exe')==command[0]+'/bin/.forgejo-runner-wrapped','STACK_RUNNER_EXECUTABLE_REFUSED')
    need(run([CTL,'show',RUNNER,'-p','RootDirectory','--value']).decode().strip()==root[0],'STACK_RUNNER_ROOT_REFUSED')
    for name in ('etc/mrjam-forgejo-runner/admission.json','var/lib/mrjam-validation-admissions',
        'run/mrjam-validation-authority/request.sock','run/mrjam-validation-collector/request.sock'):
        a=Path('/',name).stat();b=Path('/proc',str(pid),'root',name).stat()
        need((a.st_dev,a.st_ino)==(b.st_dev,b.st_ino),'STACK_RUNNER_MOUNT_REFUSED')
    return pid

def verify(target,before,statuses):
    need(os.path.realpath('/run/current-system')==target,'STACK_CURRENT_REFUSED')
    need(retained()==before and probe()==statuses,'STACK_APPLICATION_CONTINUITY_REFUSED')
    for name in ('nginx/nginx.conf','mrjam-delivery-adopted.json'):
        need(Path('/etc',name).read_bytes()==Path(OLD,'etc',name).read_bytes(),'STACK_APPLICATION_CONFIGURATION_CHANGED')
    need(not Path('/etc/mrjam-vise-delivery-adopted.json').exists(),'STACK_VISE_ADOPTION_CHANGED')
    if target==NEW:
        view=json.loads(Path(VIEW).read_bytes())
        need(os.path.realpath('/etc/mrjam-delivery-stack')==view['state']['control_plane']['stack'],'STACK_DESCRIPTOR_REFUSED')
        for name,text in view['units'].items():
            need(Path('/etc/systemd/system',name).read_text()==text,'STACK_INSTALLED_UNIT_REFUSED')
        need('mrjam-forgejo-runner.service' in run([CTL,'show','forgejo.service','-p','Wants','--value']).decode().split(),
            'STACK_RECOVERY_DEPENDENCY_REFUSED')
    else:need(not Path('/etc/mrjam-delivery-stack').exists(),'STACK_RETURN_DESCRIPTOR_REFUSED')
    return runner(target)

def transition(target,before,statuses):
    idle();inhibit(RUNNER);run([CTL,'daemon-reload']);run([CTL,'stop',RUNNER]);idle()
    run([target+'/bin/switch-to-configuration','test'])
    need(properties(RUNNER)['ActiveState']=='inactive','STACK_IMPLICIT_RUNNER_START')
    release(RUNNER);run([CTL,'daemon-reload']);run([CTL,'start',RUNNER])
    time.sleep(1)
    return verify(target,before,statuses)

def main():
    global INITIAL
    need(os.geteuid()==0 and len(sys.argv)==1 and os.uname().nodename=='srv1982677','STACK_HOST_REFUSED')
    os.umask(0o077)
    fd=os.open('/var/lib/mrjam-cutover/first-deployment/transaction.lock',os.O_RDONLY|os.O_NOFOLLOW)
    try:
        info=os.fstat(fd);need(stat.S_ISREG(info.st_mode) and info.st_uid==0 and info.st_nlink==1,'STACK_LOCK_REFUSED')
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        need(os.path.realpath('/run/current-system')==os.path.realpath(PROFILE)==OLD,'STACK_BASELINE_REFUSED')
        need(not STATE.exists() and not STATE.is_symlink() and not PERMIT.exists() and not PERMIT.is_symlink(),'STACK_EXISTING_TRANSACTION')
        for unit in WRITERS+[RUNNER]:
            for parent in ('/etc/systemd/system','/run/systemd/system'):
                directory=Path(parent,unit+'.d')
                need(not directory.exists() or not any(directory.iterdir()),'STACK_EXISTING_DROPIN')
        need(RECOVERY.is_symlink() and os.readlink(RECOVERY)=='/etc/systemd/system/'+RUNNER,'STACK_RUNTIME_RECOVERY_REFUSED')
        spec=importlib.util.spec_from_file_location('layout','/nix/store/i86qcn4qs24xsmbadxsghhbgx91zmmjj-delivery_stack_layout.py')
        layout=importlib.util.module_from_spec(spec);spec.loader.exec_module(layout)
        layout.verify(OLD,json.loads(Path(VIEW).read_bytes()))
        idle();before=retained();statuses=probe()
        need(all(p['ActiveState']=='active' and int(p['MainPID'])>0 for p in before.values()),'STACK_RETAINED_SERVICE_INACTIVE')
        runner(OLD);INITIAL={'retained':before,'https':statuses}
        STATE.mkdir(mode=0o700);checkpoint('prepared')
        boot_changed=False;installed=[]
        try:
            for unit in WRITERS:inhibit(unit);installed.append(unit)
            run([CTL,'daemon-reload']);pids=[]
            for phase,target in [('first-new',NEW),('real-return',OLD),('final-new',NEW)]:
                checkpoint(phase);pids.append(transition(target,before,statuses))
            checkpoint('boot-commit');boot_changed=True
            run(['/run/current-system/sw/bin/nix-env','--profile',PROFILE,'--set',NEW])
            run([NEW+'/bin/switch-to-configuration','boot'])
            need(os.path.realpath(PROFILE)==NEW,'STACK_BOOT_REFUSED');verify(NEW,before,statuses)
            # The declarative dependency must exist before removing the runtime repair.
            link=Path('/etc/systemd/system/forgejo.service.wants',RUNNER)
            need(link.is_file() and link.read_bytes()==Path('/etc/systemd/system',RUNNER).read_bytes(),'STACK_DECLARATIVE_RECOVERY_REFUSED')
            RECOVERY.unlink();run([CTL,'daemon-reload']);verify(NEW,before,statuses)
            checkpoint('verified',runner_pids=pids,https=statuses)
            for unit in installed:release(unit)
            run([CTL,'daemon-reload']);installed=[]
            verify(NEW,before,statuses)
            checkpoint('complete',runner_pids=pids,https=statuses)
            print(json.dumps({'code':'DELIVERY_STACK_ACTIVE_AND_BOOT','system':NEW,
                'real_return_verified':True,'retained_processes_unchanged':True,'runner_pids':pids,
                'runtime_repair_removed':True,'https':statuses,'application_deployment':False},sort_keys=True))
        except Exception as error:
            restored=False
            try:
                checkpoint('recovering')
                if not RECOVERY.is_symlink():RECOVERY.symlink_to('/etc/systemd/system/'+RUNNER)
                transition(OLD,before,statuses)
                if boot_changed:
                    run(['/run/current-system/sw/bin/nix-env','--profile',PROFILE,'--set',OLD])
                    run([OLD+'/bin/switch-to-configuration','boot'])
                need(os.path.realpath(PROFILE)==OLD,'STACK_RETURN_BOOT_REFUSED')
                verify(OLD,before,statuses)
                for unit in installed:release(unit)
                run([CTL,'daemon-reload']);restored=True
            except Exception:pass
            checkpoint('returned-after-failure' if restored else 'recovery-required')
            code=str(error) if type(error) is RuntimeError and re.fullmatch('[A-Z_]{1,80}',str(error)) else 'STACK_ACTIVATION_ERROR'
            print(json.dumps({'code':code,'previous_restored':restored}));return 2
        return 0
    finally:os.close(fd)

if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as error:
        code=str(error) if type(error) is RuntimeError and re.fullmatch('[A-Z_]{1,80}',str(error)) else 'STACK_PREFLIGHT_REFUSED'
        print(json.dumps({'code':code}));raise SystemExit(2)
