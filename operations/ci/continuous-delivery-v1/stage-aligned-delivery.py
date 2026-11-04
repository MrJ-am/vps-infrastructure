"""Fixed reviewed delivery: start inactive Rust slot, verify return, retain blue."""
import fcntl,hashlib,http.client,importlib.util,json,os,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,'/nix/store/ixhqrvgq1vixg0g0fc01lwkdprxxkmn7-mrjam-validation-admission-control-1/lib')
import contract as C
import admission_control as R
import signer as A
OLD='/nix/store/frha1lc5vwqx4d5bzs6p2hfabk8r6r49-nixos-system-srv1982677-26.05pre-git'
NEW='/nix/store/z3rr0v83aar7xnghm96840cwfr1hjdiv-nixos-system-srv1982677-26.05pre-git'
SERVER='/nix/store/jszbmj1s6h4xnzg5qgga99bzcy6i84hq-mrjam-delivery-server-04754e2c5e53'
RUNTIME='/nix/store/g8vxsl9nhmrbnn1d866yidk07zwjyv2x-mrjam-runtime-green'
DIGEST='04754e2c5e531c37bd06864ed2becb3fc218d20d780d9a8c8e1b045956a5d04d'
HEAD='5a05461e9e3eb7cf77e99b85ae8d49630f13004d'
CTL='/nix/store/0xiinbh7pbj479i5v28mqnjrvhvbdibf-systemd-260.2/bin/systemctl'
PROFILE='/nix/var/nix/profiles/system'
UNITS=['nginx.service','postgresql.service','forgejo.service','vise.service','mrjam-rust-blue.service','mrjam-forgejo-runner.service']
JOURNAL=Path('/var/lib/mrjam-delivery-captures')/(DIGEST+'.stage-003.json')
MASKS=Path('/run/mrjam-cutover/masks.json')
def run(args,capture=False,timeout=180):
    p=subprocess.run(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE if capture else subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=timeout)
    C.require(p.returncode==0,'STAGE_COMMAND_FAILED:'+Path(args[0]).name+':'+str(args[1:])+':'+str(p.returncode))
    if capture:C.require(len(p.stdout)<=65536,'OUTPUT_LIMIT');return p.stdout
def properties(unit):return run([CTL,'show',unit,'-p','MainPID','-p','ActiveState','-p','SubState'],True).decode()
def retained():return {unit:properties(unit) for unit in UNITS}
def checkpoint(phase):
    temporary=JOURNAL.with_suffix('.next')
    fd=os.open(temporary,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as f:f.write(C.canonical({'phase':phase,'old':OLD,'staged':NEW,'proposal':DIGEST}));f.flush();os.fsync(f.fileno())
    os.replace(temporary,JOURNAL)
    fd=os.open(JOURNAL.parent,os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)
def replace_masks(expected,desired):
    C.require(C.regular_file(MASKS,owner=0,mode=0o600,maximum=65536)==expected,'MASKS_CHANGED')
    temporary=MASKS.with_name('delivery-masks.next')
    fd=os.open(temporary,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as f:f.write(desired);f.flush();os.fsync(f.fileno())
    os.replace(temporary,MASKS)
    fd=os.open(MASKS.parent,os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)
    run([CTL,'daemon-reload'])
def ready():
    expected=json.loads(Path(RUNTIME+'/runtime.json').read_bytes())['required_capabilities']
    deadline=time.monotonic()+60
    while time.monotonic()<deadline:
        try:
            c=http.client.HTTPConnection('127.0.0.1',38102,timeout=3)
            c.request('GET','/readyz',headers={'Host':'audition.mrj.am'})
            r=c.getresponse();raw=r.read(8193);c.close()
            if r.status==200 and len(raw)<=8192:
                body=json.loads(raw)
                C.require(body=={'status':'ready','scope':'configured-capabilities-only','capabilities':expected},'READINESS_CONTRACT_REFUSED')
                pid=run([CTL,'show','mrjam-rust-green.service','-p','MainPID','--value'],True).decode().strip()
                C.require(os.readlink('/proc/'+pid+'/exe')==SERVER+'/libexec/mrjam-server','PROCESS_IDENTITY_REFUSED')
                return
        except (OSError,http.client.HTTPException,json.JSONDecodeError):pass
        time.sleep(.5)
    raise C.Refused('GREEN_NOT_READY')
def main():
    C.require(os.getuid()==0 and os.uname().nodename=='srv1982677','HOST_REFUSED')
    lock=os.open('/var/lib/mrjam-cutover/first-deployment/transaction.lock',os.O_RDWR|os.O_NOFOLLOW);fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    C.require(os.path.realpath('/run/current-system')==OLD and os.path.realpath(PROFILE)==OLD and not JOURNAL.exists(),'BASELINE_OR_JOURNAL_CHANGED')
    C.require('ActiveState=inactive\n' in properties('mrjam-rust-green.service'),'INACTIVE_SLOT_REQUIRED')
    policy=R.load(DIGEST)['authority']
    raw=C.regular_file(Path('/var/lib/mrjam-delivery-captures')/DIGEST/'attestation.json',owner=0,mode=0o400,maximum=C.MAX_DOCUMENT)
    envelope=C.parse(raw)
    C.require(A.verify(envelope,policy) and C.sha(raw)=='645cbd33f82d0be8dbc2eef6990ba854a3610d96476c83dc922265b7f46a1e01','ATTESTATION_REFUSED')
    server=next(a for a in envelope['payload']['artifacts'] if a['name']=='server')
    data=Path(SERVER+'/libexec/mrjam-server').read_bytes()
    C.require(len(data)==server['bytes'] and hashlib.sha256(data).hexdigest()==server['sha256'],'SERVER_BYTES_REFUSED')
    s=importlib.util.spec_from_file_location('bootstrap','/nix/store/8pkxq7pahlmhlmf6v890q2ica69cflsy-mrjam-forgejo-technical-bootstrap-1/libexec/core.py');B=importlib.util.module_from_spec(s);s.loader.exec_module(B)
    with B.governance_lease() as token:
        c=http.client.HTTPConnection('127.0.0.1',3004,timeout=5);c.request('GET','/api/v1/repos/MrJ-am/mrjam-plateforme/pulls/1',headers={'Host':'forge.mrj.am','Authorization':'token '+token});r=c.getresponse();raw=r.read(131073);c.close()
        C.require(r.status==200 and len(raw)<=131072,'MERGE_OBSERVATION_REFUSED')
        pr=json.loads(raw);C.require(pr['merged'] and pr['head']['sha']==HEAD and pr['merge_commit_sha']==HEAD,'PROTECTED_MERGE_REQUIRED')
    before=retained();C.require(all('ActiveState=active\n' in value for value in before.values()),'RETAINED_SERVICE_INACTIVE')
    original_masks=C.regular_file(MASKS,owner=0,mode=0o600,maximum=65536)
    masks=C.parse(original_masks)
    C.require(set(masks)=={'schema_version','units'} and masks['schema_version']==1 and masks['units']==sorted(set(masks['units'])) and 'mrjam-rust-green.service' in masks['units'],'MASK_RECORD_REFUSED')
    unmasked=C.canonical({'schema_version':1,'units':[u for u in masks['units'] if u!='mrjam-rust-green.service']})
    checkpoint('prepared')
    try:
        for phase,target in [('first-stage',NEW),('return',OLD),('final-stage',NEW)]:
            checkpoint(phase)
            run([target+'/bin/switch-to-configuration','test'])
            C.require(retained()==before and os.path.realpath('/run/current-system')==target and os.path.realpath(PROFILE)==OLD,'RETAINED_STATE_CHANGED')
            if target==NEW:
                replace_masks(original_masks,unmasked)
                run([CTL,'start','mrjam-rust-green.service']);ready()
                if phase=='first-stage':
                    run([CTL,'stop','mrjam-rust-green.service'],timeout=60)
                    replace_masks(unmasked,original_masks)
        C.require(retained()==before,'RETAINED_PROCESS_CHANGED')
        checkpoint('green-ready-blue-routed')
        print(json.dumps({'code':'INACTIVE_REVIEWED_DELIVERY_READY','current':NEW,'boot':OLD,'green_ready':True,'real_return_verified':True,'retained_processes_unchanged':True,'routes_changed':False,'automatic_deployment_enabled':False}))
    except Exception as error:
        restored=False
        try:
            run([CTL,'stop','mrjam-rust-green.service'],timeout=60)
            observed=C.regular_file(MASKS,owner=0,mode=0o600,maximum=65536)
            C.require(observed in (original_masks,unmasked),'MASKS_CHANGED_DURING_RETURN')
            if observed==unmasked:replace_masks(unmasked,original_masks)
            run([OLD+'/bin/switch-to-configuration','test'])
            restored=retained()==before and os.path.realpath('/run/current-system')==OLD
            checkpoint('returned-after-failure' if restored else 'recovery-required')
        except Exception:pass
        print(json.dumps({'code':'INACTIVE_STAGE_FAILED','cause':str(error) if isinstance(error,C.Refused) else type(error).__name__,'previous_restored':restored}));raise SystemExit(2)
    finally:os.close(lock)
if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps({'code':str(error) if isinstance(error,C.Refused) else 'STAGE_PREFLIGHT_FAILED','exception_type':type(error).__name__}));raise SystemExit(2)
