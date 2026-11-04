"""Service entry point; configuration paths come from the installed unit."""
import importlib.util,json,os,re,stat,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import github_proposals as P
import intake_prepare as W
import intake_bridge as B
import policy as V
import source_policy as Vise
import delivery_profiles as Profiles

STORE=re.compile(r'/nix/store/[a-z0-9]{32}-[A-Za-z0-9+._?=-]+\Z')

def immutable(path,directory=False):
    path=Path(path)
    W.Q.S.require(STORE.fullmatch(str(path)) and path.resolve()==path,'ADOPTED_STORE_PATH_REFUSED')
    info=path.lstat()
    W.Q.S.require(info.st_uid==0 and not info.st_mode&0o022
        and (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)),
        'ADOPTED_STORE_METADATA_REFUSED')
    return path

def adopted_base(proposal):
    profile=Profiles.selected(proposal)
    # Paths are installed unit configuration, never fields from the proposal.
    # No ViSe descriptor is configured until its entire admission and delivery
    # path is qualified; never fall back to the platform's adopted sources.
    selected_path=os.environ.get('MRJAM_ADOPTED_BASE' if profile=='platform' else 'MRJAM_VISE_ADOPTED_BASE')
    W.Q.S.require(type(selected_path) is str and bool(selected_path),'PROJECT_RECIPE_UNAVAILABLE')
    validator=V if profile=='platform' else Vise
    # The /etc link is installed by NixOS; only its immutable store target is
    # consumed. Future promotions must advance this descriptor with the code.
    descriptor=immutable(Path(selected_path).resolve(strict=True))
    W.Q.S.require(descriptor.stat().st_size<=65536,'ADOPTED_DESCRIPTOR_LIMIT')
    adopted=json.loads(descriptor.read_bytes())
    W.Q.S.require(type(adopted) is dict and set(adopted)=={'schema_version','source','policy','proposal_sha256'}
        and adopted['schema_version']==1,'ADOPTED_DESCRIPTOR_FIELDS')
    base=immutable(adopted['source'],directory=True);policy_path=immutable(adopted['policy'])
    policy=validator.checked_policy(validator.read_json(policy_path))
    return base,adopted['proposal_sha256'],policy,validator

def main():
    state=W.private_directory(Path(os.environ['STATE_DIRECTORY']).resolve(strict=True))
    spool=state/'prepared'
    try:spool.mkdir(mode=0o700)
    except FileExistsError:pass
    # The unit mounts a fresh, size-limited tmpfs at /tmp for each run.
    # Never let the transport fall back to the persistent state filesystem.
    mounts=Path('/proc/self/mountinfo').read_text().splitlines()
    W.Q.S.require(any(line.split()[4]=='/tmp' and line.split(' - ')[1].split()[0]=='tmpfs'
        for line in mounts),'INTAKE_TMPFS_REQUIRED')
    scratch=Path('/tmp/mrjam-intake');scratch.mkdir(mode=0o700)
    scratch=W.private_directory(scratch)
    credential=Path(os.environ['CREDENTIALS_DIRECTORY'])/'github-app'
    fd=os.open(credential,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        P.credential_metadata(os.fstat(fd),os.getuid(),os.getgid())
        credentials=P.A.checked(json.loads(os.read(fd,32769)))
    finally:os.close(fd)
    gate_path=Path(__file__).resolve().parent/'check_git_tree.py'
    spec=importlib.util.spec_from_file_location('tree_gate',gate_path)
    gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
    queue=W.Q.Queue(state)
    try:
        decisions=os.environ.get('MRJAM_INTAKE_DECISIONS')
        if decisions:B.decisions(queue,spool,decisions,int(time.time()))
        result=W.once(queue,spool,scratch,None,None,None,
            git=os.environ['MRJAM_INTAKE_GIT'],credentials=credentials,
            validator_policy=V,gate=gate,gate_path=gate_path,select_base=adopted_base)
        if decisions:result['ready_exported']=B.export(queue,spool,state)
    finally:queue.close()
    print(json.dumps(result))

if __name__=='__main__':
    try:main()
    except Exception:
        print('{"code":"INTAKE_PREPARATION_UNAVAILABLE","deployment_authorized":false}')
        raise SystemExit(2) from None
