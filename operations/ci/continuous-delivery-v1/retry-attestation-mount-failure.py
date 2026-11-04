"""Retry only run4's attestation failure after restoring the runner mounts."""
import fcntl,http.client,json,os,sys,time
from pathlib import Path
sys.path.insert(0,'/nix/store/dlphwj3kmxmljjg4dj6flihqah9jghgy-mrjam-protected-admission-controller-1/lib')
import admission_orchestrator as O
import validation_dispatch as D
from source_snapshot import require
ROOT=Path('/var/lib/mrjam-intake-admission')
JOB='18ff551f7e7062936b962f6d162a2835a43df087795456c9bf46e7b447a7f230'
DIGEST='e06f030310aed4f8ff1cb0c5b836848dfcd9d4e99b926c841f7619b477fdd7e7'
def main():
    require(os.getuid()==0 and os.path.realpath('/run/current-system')==
        '/nix/store/mp6b02wzn3pj5fn1g8j8gp9nzfr4fsq0-nixos-system-srv1982677-26.05pre-git','REPAIRED_HOST_REQUIRED')
    with open('/var/lib/mrjam-cutover/first-deployment/transaction.lock','rb') as adoption,open(ROOT/'controller.lock','rb') as controller:
        fcntl.flock(adoption,fcntl.LOCK_EX|fcntl.LOCK_NB);fcntl.flock(controller,fcntl.LOCK_EX|fcntl.LOCK_NB)
        path=ROOT/'jobs'/JOB/'state.json';value=O.read(path)
        require(value['phase']=='failed' and value['run']['id']==4 and value['run']['status']=='failure'
            and value['capture']['proposal_sha256']==DIGEST and 'attestation_recovery' not in value,'RECOVERY_STATE_REFUSED')
        token=Path('/var/lib/mrjam-ci-credentials/forgejo-registration-token').read_text().strip()
        def get(suffix):
            c=http.client.HTTPConnection('127.0.0.1',3004,timeout=20)
            try:
                c.request('GET',D.BASE+suffix,headers={'Host':'forge.mrj.am','Authorization':'token '+token})
                r=c.getresponse();raw=r.read(1048577)
                require(r.status==200 and len(raw)<=1048576,'RECOVERY_API_REFUSED');return raw
            finally:c.close()
        run=D.identify(json.loads(get('/actions/runs/4')),DIGEST,value['run']['rules_revision'])
        require(run and run['terminal'] and run['status']=='failure','RECOVERY_RUN_CHANGED')
        lines=get('/actions/jobs/4/logs').decode('utf-8').splitlines()
        require(len(lines)==1 and lines[0].endswith(' MRJAM_ATTESTATION_REFUSED'),'RECOVERY_CAUSE_CHANGED')
        value['attestation_recovery']={'previous_run':value['run'],'reason':'RUNNER_ADMISSION_MOUNTS_RESTORED','at':int(time.time())}
        value.update(phase='constructed',code=None,next_attempt=int(time.time()),updated=int(time.time()))
        value.pop('run');value.pop('after_id',None)
        O.save(path,value)
        print(json.dumps({'code':'FAILED_ATTESTATION_REQUEUED_AFTER_MOUNT_REPAIR','previous_run':4,'job':JOB,'deployed':False}))
if __name__=='__main__':main()
