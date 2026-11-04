"""One persistent intake claim -> exact, verified sources and durable receipt.

No candidate program, signing, admission or deployment. The caller supplies
the protected adopted base, validator and a private size-limited scratch mount.
The protected admission consumer must independently observe GitHub and verify
the copied source and policy, regardless of this worker's receipt.
"""
import fcntl,json,os,re,shutil,stat,tempfile,time
from pathlib import Path

import intake_queue as Q
import proposal_prepare as C
import source_fetch as F

MAX_RESULTS=16

def private_directory(path):
    path=Path(path);info=path.lstat()
    Q.S.require(path.is_absolute() and path.resolve()==path and stat.S_ISDIR(info.st_mode)
        and info.st_uid==os.getuid() and stat.S_IMODE(info.st_mode)==0o700,'PREPARATION_DIRECTORY_REFUSED')
    return path

def read_file(path,limit):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        info=os.fstat(fd)
        Q.S.require(stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and info.st_nlink==1
            and info.st_size<=limit,'PREPARATION_FILE_REFUSED')
        with os.fdopen(fd,'rb',closefd=False) as stream:raw=stream.read(limit+1)
        Q.S.require(len(raw)==info.st_size,'PREPARATION_FILE_CHANGED')
        return raw
    finally:os.close(fd)

def sync_directory(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)

def persist_tree(root):
    # Only the freshly constructed result is traversed, under the process lock.
    for directory,dirs,files in os.walk(root,topdown=False,followlinks=False):
        for name in files:
            fd=os.open(Path(directory)/name,os.O_RDONLY|os.O_NOFOLLOW)
            try:
                Q.S.require(stat.S_ISREG(os.fstat(fd).st_mode),'PREPARATION_FILE_REFUSED')
                os.fsync(fd)
            finally:os.close(fd)
        sync_directory(directory)

def binding(claim,base_digest,base_policy):
    Q.S.require(type(base_digest) is str and re.fullmatch('[0-9a-f]{64}',base_digest),'ADOPTED_DIGEST_REFUSED')
    return {'schema_version':1,'job_key':claim['key'],'proposal':claim['proposal'],
        'base_sha256':base_digest,'base_policy_sha256':C.sha(C.encode(base_policy))}

def verified_result(target,identity,validator_policy,gate_path):
    private_directory(target)
    Q.S.require(set(p.name for p in target.iterdir())=={'source','policy.json','receipt.json'},'PREPARATION_RESULT_FIELDS')
    raw=read_file(target/'receipt.json',65536);receipt=json.loads(raw)
    Q.S.require(type(receipt) is dict and set(receipt)==set(identity)|{'proposal_sha256','policy_sha256','deployment_authorized'}
        and all(receipt[k]==v for k,v in identity.items()) and receipt['deployment_authorized'] is False,
        'PREPARATION_RECEIPT_REFUSED')
    policy_raw=read_file(target/'policy.json',1024*1024)
    Q.S.require(C.sha(policy_raw)==receipt['policy_sha256'],'PREPARATION_POLICY_REFUSED')
    policy=validator_policy.checked_policy(json.loads(policy_raw))
    private_directory(target/'source')
    _,digest=validator_policy.verify_sources(target/'source',policy,gate_path)
    Q.S.require(digest==receipt['proposal_sha256'],'PREPARATION_SOURCE_REFUSED')
    return C.sha(raw)

def once(queue,spool,scratch,base,base_digest,base_policy,*,git,credentials,
         validator_policy,gate,gate_path,clock=time.time,receive=F.receive,select_base=None):
    """Process at most one job. Caller must not change adopted inputs in place.

    A crash after atomic publication but before SQLite completion reuses the
    complete result only after rechecking its manifest and every source byte.
    An interrupted unpublished result is confined to a temporary directory.
    """
    spool=private_directory(spool);scratch=private_directory(scratch)
    fd=os.open(spool/'prepare.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        info=os.fstat(fd)
        Q.S.require(stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and info.st_nlink==1
            and stat.S_IMODE(info.st_mode)==0o600,'PREPARATION_LOCK_REFUSED')
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return {'code':'PREPARATION_BUSY'}
        # Only this process-owned, unpublished staging name is disposable.
        # Completed receipts are never removed by the intake worker.
        staging=spool/'.incomplete'
        if staging.exists() or staging.is_symlink():
            private_directory(staging);shutil.rmtree(staging);sync_directory(spool)
        claim=queue.claim(int(clock()))
        if claim is None:return {'code':'PREPARATION_IDLE'}
        try:
            # Installed code selects the target's current adoption only after
            # claiming a job. A broken/missing ViSe profile must not prevent
            # the queue from processing an independent platform proposal.
            if select_base is not None:
                base,base_digest,base_policy,validator_policy=select_base(claim['proposal'])
            identity=binding(claim,base_digest,base_policy)
            name=C.sha(C.encode(identity));target=spool/name
            sources=[s for s in base_policy['sources'] if s['repository']=='MrJ-am/'+claim['proposal']['repository']]
            Q.S.require(bool(sources),'PROJECT_RECIPE_UNAVAILABLE')
            if target.exists() or target.is_symlink():
                receipt=verified_result(target,identity,validator_policy,gate_path)
            else:
                # Never delete another result to make room. The protected
                # consumer acknowledges and retires retained results later.
                Q.S.require(len([p for p in spool.iterdir() if re.fullmatch('[0-9a-f]{64}',p.name)])<MAX_RESULTS,
                    'PREPARATION_CAPACITY_REACHED')
                with tempfile.TemporaryDirectory(prefix='receive-',dir=scratch) as work:
                    reader=receive(Path(work),git,claim['proposal'],credentials)
                    updates={s['id']:{'reader':reader,'base':claim['proposal']['base'],'head':claim['proposal']['head']} for s in sources}
                    # Same filesystem as the final result: rename is atomic.
                    staging.mkdir(mode=0o700)
                    try:
                        result=staging/'result';result.mkdir(mode=0o700)
                        prepared=C.prepare(base,base_digest,base_policy,updates,result/'source',
                            validator_policy=validator_policy,gate=gate,gate_path=gate_path)
                        policy_raw=C.encode(prepared['policy']);(result/'policy.json').write_bytes(policy_raw)
                        receipt_raw=C.encode({**identity,'proposal_sha256':prepared['proposal_sha256'],
                            'policy_sha256':C.sha(policy_raw),'deployment_authorized':False})
                        (result/'receipt.json').write_bytes(receipt_raw)
                        receipt=verified_result(result,identity,validator_policy,gate_path)
                        persist_tree(result);os.rename(result,target);sync_directory(spool)
                    finally:
                        shutil.rmtree(staging);sync_directory(spool)
            queue.finish(claim,int(clock()),receipt=receipt)
            return {'code':'PREPARATION_READY','key':claim['key'],'result':name,'receipt':receipt,
                'admission_performed':False,'deployment_authorized':False}
        except Exception as error:
            # Do not export source text, transport diagnostics or credentials.
            code=str(error) if isinstance(error,Q.S.Refused) else 'SOURCE_PREPARATION_REFUSED'
            if not re.fullmatch('[A-Z_]{1,80}',code):code='SOURCE_PREPARATION_REFUSED'
            try:queue.finish(claim,int(clock()),code=code)
            except Q.S.Refused:pass  # An expired lease is recovered by claim().
            return {'code':code,'key':claim['key'],'deployment_authorized':False}
    finally:os.close(fd)
