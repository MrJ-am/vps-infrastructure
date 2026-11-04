"""Bounded first real mirror using its own non-admin Forgejo identity."""
import fcntl,json,os,re,sys,tempfile
from pathlib import Path
sys.path.insert(0,'/nix/store/dlphwj3kmxmljjg4dj6flihqah9jghgy-mrjam-protected-admission-controller-1/lib')
sys.path.insert(0,'/nix/store/ixhqrvgq1vixg0g0fc01lwkdprxxkmn7-mrjam-validation-admission-control-1/lib')
sys.path.insert(0,str(Path(__file__).resolve().parent))
import admission_control as A,contract as C,signer,admission_orchestrator as O
import github_proposals as P,source_observation as S,forge_proposal as M
JOB=Path('/var/lib/mrjam-intake-admission/jobs/18ff551f7e7062936b962f6d162a2835a43df087795456c9bf46e7b447a7f230')
DIGEST='e06f030310aed4f8ff1cb0c5b836848dfcd9d4e99b926c841f7619b477fdd7e7'
HEAD='e4cc836d76c4104b4d356e583a2e5f34a827f90b'
def credential(name):
    p=Path(os.environ['CREDENTIALS_DIRECTORY'])/name
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        P.credential_metadata(os.fstat(fd),os.getuid(),os.getgid());return os.read(fd,32769)
    finally:os.close(fd)
def main():
    C.require(os.getuid()==0 and len(sys.argv)==1 and os.uname().nodename=='srv1982677','MIRROR_HOST_REFUSED')
    C.require(os.path.realpath('/run/current-system')=='/nix/store/mp6b02wzn3pj5fn1g8j8gp9nzfr4fsq0-nixos-system-srv1982677-26.05pre-git','MIRROR_BASELINE_REFUSED')
    C.require(any(line.split()[4]=='/tmp' and line.split(' - ')[1].split()[0]=='tmpfs'
        for line in Path('/proc/self/mountinfo').read_text().splitlines()),'MIRROR_TMPFS_REQUIRED')
    state=Path(os.environ['STATE_DIRECTORY']);O.W.private_directory(state)
    with open('/var/lib/mrjam-cutover/first-deployment/transaction.lock','rb') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        value=O.read(JOB/'state.json');capture=value['capture'];proposal=capture['proposal']
        C.require(value['phase']=='validated' and capture['proposal_sha256']==DIGEST
            and proposal['head']==HEAD and value['run']['id']==5 and value['run']['status']=='success','MIRROR_JOB_REFUSED')
        policy=A.load(DIGEST)['authority']
        envelope=C.parse(C.regular_file(JOB/'artifacts/attestation.json',owner=0,mode=0o400,maximum=C.MAX_DOCUMENT))
        C.require(signer.verify(envelope,policy) and envelope['payload']['proposal_sha256']==DIGEST,'MIRROR_SIGNATURE_REFUSED')
        for item in envelope['payload']['artifacts']:
            raw=C.regular_file(JOB/'artifacts'/item['name'],owner=0,mode=0o400,maximum=dict(C.ARTIFACTS)[item['name']])
            C.require(len(raw)==item['bytes'] and C.sha(raw)==item['sha256'],'MIRROR_ARTIFACT_CHANGED')
        bindings=[s for s in policy['sources'] if s['repository']=='MrJ-am/'+proposal['repository'] and s['revision']==HEAD]
        C.require(len(bindings)==1,'MIRROR_SOURCE_BINDING_REFUSED')
        expected={k:bindings[0][k] for k in ['repository','revision','tree_sha']}
        github=P.A.checked(C.parse(credential('github-app'),32768))
        C.require(S.observe(proposal,github)==expected,'MIRROR_REMOTE_SOURCE_CHANGED')
        token=credential('forgejo-mirror').decode().strip();observer=credential('forgejo-observer').decode().strip()
        api=M.API(proposal['repository'],M.branch_name(proposal),token,observer)
        with tempfile.TemporaryDirectory(prefix='mrjam-mirror-',dir='/tmp') as directory:
            result=M.mirror(proposal,DIGEST,5,api,lambda branch:M.transfer(directory,os.environ['MRJAM_MIRROR_GIT'],
                proposal,expected,github,token,branch))
        temporary=state/'receipt.next';destination=state/'receipt.json'
        fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as out:out.write(C.canonical(result));out.flush();os.fsync(out.fileno())
        os.replace(temporary,destination);O.W.sync_directory(state)
        print(json.dumps({'code':'VALIDATED_PROPOSAL_MIRRORED',**result}))
if __name__=='__main__':
    try:main()
    except Exception as error:
        code=str(error) if type(error).__name__=='Refused' and re.fullmatch('[A-Z_]{1,80}',str(error)) else 'VALIDATED_MIRROR_REFUSED'
        print(json.dumps({'code':code,'exception_type':type(error).__name__}));raise SystemExit(2) from None
