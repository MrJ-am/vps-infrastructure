"""One fixed identity/stage per systemd entry point; no caller arguments."""
import fcntl,json,os,re,sys
from pathlib import Path
ADMISSION='/nix/store/qmzbv6zskr9qzhh3ifqs010jz26q2jlh-mrjam-protected-admission-controller-1'
ANCHOR='/nix/store/ixhqrvgq1vixg0g0fc01lwkdprxxkmn7-mrjam-validation-admission-control-1'
ENABLE_VISE=False
RECIPE='@delivery-recipe@'
sys.path.insert(0,ADMISSION+'/lib')
sys.path.insert(0,ANCHOR+'/lib')
sys.path.insert(0,str(Path(__file__).resolve().parent))
import contract as C,github_proposals as G
import acceptance_pipeline as P,acceptance_adapter as A,acceptance_commit as K
import staging_gate as T
import delivery_profiles as Profiles

def staging_check(state,jobs,job,verify):
    if Profiles.selected(job['capture']['proposal'])=='platform':
        return T.ready(Path('/var/lib/mrjam-staging'),job)
    C.require(ENABLE_VISE,'ACCEPTANCE_PROFILE_NOT_INSTALLED')
    sys.path.extend([str(Path(RECIPE)/'operations/vise/delivery'),
        str(Path(RECIPE)/'operations/ci/continuous-delivery-v1')])
    import acceptance_gate as V
    return V.ready(state,jobs,Path('/var/lib/mrjam-delivery-preparation'),
        Path('/var/lib/mrjam-staging'),job,verify,
        recipe=Path(RECIPE)/'operations/vise/delivery/generations.nix')

def credential(name):
    path=Path(os.environ['CREDENTIALS_DIRECTORY'])/name
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:G.credential_metadata(os.fstat(fd),os.getuid(),os.getgid());return os.read(fd,32769)
    finally:os.close(fd)

def main():
    C.require(os.getuid()==0 and len(sys.argv)==1 and os.uname().nodename=='srv1982677','ACCEPTANCE_HOST_REFUSED')
    stage=os.environ['MRJAM_ACCEPTANCE_STAGE'];C.require(stage in P.STAGES,'ACCEPTANCE_STAGE_REFUSED')
    C.require(any(line.split()[4]=='/tmp' and line.split(' - ')[1].split()[0]=='tmpfs'
        for line in Path('/proc/self/mountinfo').read_text().splitlines()),'ACCEPTANCE_TMPFS_REQUIRED')
    state=P.O.W.private_directory(Path(os.environ['STATE_DIRECTORY']))
    with open('/var/lib/mrjam-cutover/first-deployment/transaction.lock','rb') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:print('{"code":"ACCEPTANCE_ENVIRONMENT_BUSY"}');return
        github=G.A.checked(C.parse(credential('github-app'),32768))
        token=None if stage=='sync' else credential('forgejo-role').decode().strip()
        jobs=Path('/var/lib/mrjam-intake-admission/jobs')
        adapter=A.Adapter(stage,github,credential('forgejo-observer').decode().strip(),token,os.environ['MRJAM_ACCEPTANCE_GIT'],
            commit=lambda job:K.acquire(state,jobs,job),
            staged=lambda job:staging_check(state,jobs,job,adapter.verified),enable_vise=ENABLE_VISE)
        print(json.dumps(P.tick(stage,jobs,state,adapter)))

if __name__=='__main__':
    try:main()
    except Exception as error:
        code=str(error) if type(error).__name__=='Refused' and re.fullmatch('[A-Z_]{1,80}',str(error)) else 'ACCEPTANCE_SERVICE_RETRY'
        print(json.dumps({'code':code,'exception_type':type(error).__name__}));raise SystemExit(2) from None
