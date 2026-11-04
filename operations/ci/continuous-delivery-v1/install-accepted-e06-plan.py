"""Preflight and durably enqueue the first accepted plan; fixed inputs only."""
import fcntl,json,os,re,sys,tempfile
from pathlib import Path
sys.path.insert(0,'@runtime@/lib')
import promotion_service as S
C=S.C;O=S.O
OLD='@old@';NEW='@new@'
JOB='18ff551f7e7062936b962f6d162a2835a43df087795456c9bf46e7b447a7f230'
DIGEST='e06f030310aed4f8ff1cb0c5b836848dfcd9d4e99b926c841f7619b477fdd7e7'
STATE=Path('/var/lib/mrjam-promotion')
def main():
    C.require(os.getuid()==0 and len(sys.argv)==1 and os.uname().nodename=='srv1982677','PLAN_HOST_REFUSED')
    with open('/var/lib/mrjam-cutover/first-deployment/transaction.lock','rb') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        C.require(S.R.actual()==(OLD,OLD) and not (STATE/'plan.json').exists(),'PLAN_BASELINE_REFUSED')
        job=O.read(Path('/var/lib/mrjam-intake-admission/jobs')/JOB/'state.json')
        C.require(job['phase']=='validated' and job.get('promotion') is None
            and job['capture']['proposal_sha256']==DIGEST,'PLAN_JOB_REFUSED')
        review=C.parse(C.regular_file('/var/lib/mrjam-forge-reviews-first/receipt.json',owner=0,mode=0o600,maximum=65536))
        plan={'schema_version':1,'job':JOB,'proposal_sha256':DIGEST,'old':OLD,'new':NEW,'slot':'blue',
            'bundle':'/nix/store/cqajrssk884jfr32mh65kr0gr13id2im-mrjam-delivery-bundle-e06f030310ae-blue',
            'forge_pull':2,'review':review}
        with tempfile.TemporaryDirectory(prefix='e06-plan-preflight-',dir='/var/lib/mrjam-delivery-captures') as directory:
            temp=Path(directory);O.save(temp/'plan.json',plan)
            adapter=S.Adapter(temp);adapter.authorize()
            adapter.ready('new');adapter.ready('old');adapter.verify('old',boot=True)
            key=adapter.key
        # Retain both system closures across a crash and the tested return.
        # These direct Nix GC roots contain only code/configuration references.
        roots=Path('/nix/var/nix/gcroots/mrjam-delivery')
        roots.mkdir(mode=0o700,exist_ok=True);O.W.private_directory(roots)
        for name,path in [('old',OLD),('new',NEW)]:
            link=roots/(key+'-'+name)
            if link.is_symlink():C.require(os.readlink(link)==path,'PLAN_GC_ROOT_COLLISION')
            else:os.symlink(path,link)
        O.W.sync_directory(roots)
        STATE.mkdir(mode=0o700,exist_ok=True);O.W.private_directory(STATE)
        C.require(not (STATE/'plan.json').exists(),'PLAN_ALREADY_PRESENT')
        O.save(STATE/'plan.json',plan)
    S.run([S.CTL,'start','mrjam-promotion.service'])
    journal=C.parse(C.regular_file(STATE/(key+'.json'),owner=0,mode=0o600,maximum=65536))
    result=O.read(Path('/var/lib/mrjam-intake-admission/jobs')/JOB/'state.json')
    C.require(journal['phase']=='complete' and result['phase']=='deployed'
        and result['delivery']['plan_sha256']==key and S.R.actual()==(NEW,NEW),'PLAN_DELIVERY_NOT_COMPLETE')
    print(json.dumps({'code':'ACCEPTED_E06_DELIVERY_COMPLETE','plan_sha256':key,'current':NEW,'boot':NEW,
        'job_phase':result['phase'],'real_return_verified':True,'previous_closure_retained':True,
        'public_slot':'blue','generic_automatic_intake_to_delivery':False}))
if __name__=='__main__':
    try:main()
    except Exception as error:
        code=str(error) if type(error).__name__=='Refused' and re.fullmatch('[A-Z_]{1,80}',str(error)) else 'ACCEPTED_PLAN_RETRY_REQUIRED'
        print(json.dumps({'code':code,'exception_type':type(error).__name__}));raise SystemExit(2) from None
