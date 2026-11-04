"""Installed root controller entry point; no caller arguments or free commands."""
import fcntl,json,os,re,stat,sys,traceback
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
ANCHOR_CONTROL='/nix/store/ixhqrvgq1vixg0g0fc01lwkdprxxkmn7-mrjam-validation-admission-control-1'
ENABLE_VISE=False
sys.path.insert(0,ANCHOR_CONTROL+'/lib')
import contract as C,admission_registry as R,admission_control as A,signer
import github_proposals as P
import policy as V
import stage_sources
import intake_capture as I
import admission_orchestrator as O
from admission_adapter import Adapter
from admission_profiles import Profiles

def credential(name):
    path=Path(os.environ['CREDENTIALS_DIRECTORY'])/name
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        P.credential_metadata(os.fstat(fd),os.getuid(),os.getgid())
        return os.read(fd,32769)
    finally:os.close(fd)

def main():
    C.require(os.getuid()==0 and len(sys.argv)==1,'CONTROLLER_ROOT_REQUIRED');os.umask(0o077)
    root=Path(os.environ['STATE_DIRECTORY']).resolve(strict=True);O.W.private_directory(root)
    intake=Path(os.environ.get('MRJAM_INTAKE_STATE','/var/lib/private/mrjam-github-discovery'))
    C.require(str(intake) in {'/var/lib/private/mrjam-github-discovery',
        '/var/lib/private/mrjam-intake-controller-qualification'},'CONTROLLER_INTAKE_PATH_REFUSED')
    owner=intake.lstat().st_uid;source=I.directory(intake,owner)
    try:
        try:raw=I.read(source,'ready.json',owner,65536)
        except FileNotFoundError:
            print('{"code":"CONTROLLER_BRIDGE_NOT_READY","deployment_authorized":false}');return
    finally:os.close(source)
    snapshot=C.parse(raw,65536);C.exact(snapshot,{'schema_version','ready','deployment_authorized'})
    C.require(snapshot['schema_version']==1 and snapshot['deployment_authorized'] is False,'CONTROLLER_SNAPSHOT_REFUSED')
    lock=os.open('/var/lib/mrjam-cutover/first-deployment/transaction.lock',os.O_RDWR|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        info=os.fstat(lock);C.require(stat.S_ISREG(info.st_mode) and info.st_uid==0 and info.st_nlink==1
            and not info.st_mode&0o022,'CONTROLLER_ADOPTION_LOCK_REFUSED')
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            print('{"code":"CONTROLLER_ADOPTION_BUSY","deployment_authorized":false}');return
        credentials=P.A.checked(C.parse(credential('github-app'),32768))
        token=credential('forgejo-dispatch').decode('ascii').strip()
        C.require(0<len(token)<=4096 and all(33<=ord(c)<=126 for c in token),'CONTROLLER_TOKEN_REFUSED')
        common=dict(state=intake,
            decisions='/var/lib/mrjam-intake-decisions',recipe=os.environ['MRJAM_ADMISSION_RECIPE'],
            nix_build=os.environ['MRJAM_NIX_BUILD'],credentials=credentials,forge_token=token,
            gate_path=HERE/'check_git_tree.py',contract=C,registry=R,control=A,
            signer=signer,stager=stage_sources,anchor_control=ANCHOR_CONTROL)
        platform=Adapter(adopted_path='/etc/mrjam-delivery-adopted.json',validator_policy=V,**common)
        vise=None
        if ENABLE_VISE:
            import source_policy as VP
            vise=Adapter(adopted_path='/etc/mrjam-vise-delivery-adopted.json',
                validator_policy=VP,profile='vise-v1',**common)
        adapter=Profiles(platform,vise=vise)
        print(json.dumps(O.tick(root,snapshot['ready'],adapter)))
    finally:os.close(lock)

if __name__=='__main__':
    try:main()
    except Exception as error:
        frames=traceback.extract_tb(error.__traceback__)
        code=str(error) if type(error).__name__=='Refused' else 'ADMISSION_CONTROLLER_UNAVAILABLE'
        if not re.fullmatch('[A-Z_]{1,80}',code):code='ADMISSION_CONTROLLER_UNAVAILABLE'
        print(json.dumps({'code':code,'exception_type':type(error).__name__,
            'source':Path(frames[-1].filename).name,'line':frames[-1].lineno,'deployment_authorized':False}))
        raise SystemExit(2) from None
