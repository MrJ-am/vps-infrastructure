"""Fixed graceful traffic transition, real return, then persistent boot profile."""
import fcntl,http.client,json,os,ssl,sys,time
from pathlib import Path
sys.path.insert(0,'@delivery-lib@')
import stage as S
C=S.C
NEW='/nix/store/xrh880q8hiv7c4v7cng5mi1vg4j6p264-nixos-system-srv1982677-26.05pre-git'
STAGED=S.NEW
BOOT=S.OLD
STATE=Path('/var/lib/mrjam-delivery-captures')/(S.DIGEST+'.promotion.json')
UNITS=S.UNITS+['mrjam-rust-green.service']
def retained():return {unit:S.properties(unit) for unit in UNITS}
def checkpoint(phase):
    temporary=STATE.with_suffix('.next')
    fd=os.open(temporary,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as out:
        out.write(C.canonical({'phase':phase,'staged':STAGED,'promoted':NEW,'previous_boot':BOOT,'proposal':S.DIGEST}));out.flush();os.fsync(out.fileno())
    os.replace(temporary,STATE)
    fd=os.open(STATE.parent,os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)
def https():
    context=ssl.create_default_context(cafile='/etc/ssl/certs/ca-certificates.crt')
    result={}
    for host,allowed in [('audition.mrj.am',[200]),('log.mrj.am',[200]),('logique.echos.systems',[200]),('vision.mrj.am',[200]),('vise.mrj.am',[200]),('forge.mrj.am',[200,303]),('principiipetit.io',[200])]:
        c=http.client.HTTPSConnection(host,443,timeout=10,context=context)
        path='/matheval/' if host=='principiipetit.io' else '/'
        try:
            c.request('GET',path);r=c.getresponse();status=r.status
            # Public response bodies are deliberately not exported or retained.
            r.read(1024);C.require(status in allowed,'HTTPS_STATUS_REFUSED');result[host]=status
        finally:c.close()
    return result
def main():
    C.require(os.getuid()==0 and os.uname().nodename=='srv1982677','HOST_REFUSED')
    lock=os.open('/var/lib/mrjam-cutover/first-deployment/transaction.lock',os.O_RDWR|os.O_NOFOLLOW);fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    C.require(os.path.realpath('/run/current-system')==STAGED and os.path.realpath(S.PROFILE)==BOOT and not STATE.exists(),'BASELINE_CHANGED')
    prior=json.loads(C.regular_file(S.JOURNAL,owner=0,mode=0o600,maximum=65536))
    C.require(prior['phase']=='green-ready-blue-routed' and prior['staged']==STAGED,'STAGE_NOT_ACCEPTED')
    policy=S.R.load(S.DIGEST)['authority']
    raw=C.regular_file(Path('/var/lib/mrjam-delivery-captures')/S.DIGEST/'attestation.json',owner=0,mode=0o400,maximum=C.MAX_DOCUMENT)
    C.require(S.A.verify(C.parse(raw),policy) and C.sha(raw)=='645cbd33f82d0be8dbc2eef6990ba854a3610d96476c83dc922265b7f46a1e01','ATTESTATION_REFUSED')
    blue=Path(STAGED+'/etc/nginx/nginx.conf').read_bytes();green=Path(NEW+'/etc/nginx/nginx.conf').read_bytes()
    C.require(blue.count(b'127.0.0.1:38101')==11 and blue.replace(b'127.0.0.1:38101',b'127.0.0.1:38102')==green,'ROUTE_DIFF_REFUSED')
    S.ready();before=retained();C.require(all('ActiveState=active\n' in x for x in before.values()),'RETAINED_SERVICE_INACTIVE')
    before_https=https();boot_changed=False
    checkpoint('prepared')
    try:
        for phase,target in [('first-green',NEW),('real-return-blue',STAGED),('final-green',NEW)]:
            checkpoint(phase);S.run([target+'/bin/switch-to-configuration','test'])
            C.require(os.path.realpath('/run/current-system')==target and retained()==before,'PROCESS_OR_GENERATION_CHANGED')
            C.require(Path('/etc/nginx/nginx.conf').read_bytes()==(green if target==NEW else blue),'ROUTE_NOT_INSTALLED')
            S.ready();https()
        checkpoint('green-verified-before-boot')
        boot_changed=True
        S.run(['/run/current-system/sw/bin/nix-env','--profile',S.PROFILE,'--set',NEW])
        S.run([NEW+'/bin/switch-to-configuration','boot'])
        C.require(os.path.realpath(S.PROFILE)==NEW and os.path.realpath('/run/current-system')==NEW and retained()==before,'BOOT_OR_PROCESS_REFUSED')
        after_https=https();checkpoint('green-active-and-boot-blue-retained')
        print(json.dumps({'code':'REVIEWED_DELIVERY_PROMOTED','current':NEW,'boot':NEW,'active_slot':'green','previous_blue_retained':True,'real_return_verified':True,'retained_processes_unchanged':True,'https':after_https,'automatic_future_deployment_enabled':False},sort_keys=True))
    except Exception as error:
        restored=False
        try:
            S.run([STAGED+'/bin/switch-to-configuration','test'])
            if boot_changed:
                S.run(['/run/current-system/sw/bin/nix-env','--profile',S.PROFILE,'--set',BOOT]);S.run([BOOT+'/bin/switch-to-configuration','boot'])
            restored=os.path.realpath('/run/current-system')==STAGED and os.path.realpath(S.PROFILE)==BOOT and retained()==before
            https();checkpoint('returned-blue-after-failure' if restored else 'recovery-required')
        except Exception:pass
        print(json.dumps({'code':'PROMOTION_FAILED','cause':str(error) if isinstance(error,C.Refused) else type(error).__name__,'previous_restored':restored}));raise SystemExit(2)
    finally:os.close(lock)
if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps({'code':str(error) if isinstance(error,C.Refused) else 'PROMOTION_PREFLIGHT_FAILED','exception_type':type(error).__name__}));raise SystemExit(2)
