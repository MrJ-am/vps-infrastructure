"""Protected, bounded copy and independent verification of an intake result.

The intake principal is untrusted here. Every source component is opened through
directory FDs without following links. Remote commit/tree metadata comes from
the protected caller's observer, never from the receipt. No candidate executes.
"""
import json,os,re,shutil,stat
from pathlib import Path,PurePosixPath
import intake_queue as Q
import intake_prepare as W
import proposal_policy as V
from proposal_prepare import encode,sha

def require(value,code='INTAKE_CAPTURE_REFUSED'):Q.S.require(value,code)

def directory(path,owner):
    path=Path(path)
    require(path.is_absolute() and '..' not in path.parts,'CAPTURE_DIRECTORY_REFUSED')
    fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)
    try:
        for part in path.parts[1:]:
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=fd)
            os.close(fd);fd=child
        info=os.fstat(fd)
        require(info.st_uid==owner and stat.S_IMODE(info.st_mode)==0o700,'CAPTURE_DIRECTORY_REFUSED')
        return fd
    except BaseException:os.close(fd);raise

def read(root,name,owner,limit):
    parts=PurePosixPath(name).parts
    require(type(name) is str and name and not name.startswith('/')
        and str(PurePosixPath(name))==name and all(p not in ('.','..') for p in parts),'CAPTURE_PATH_REFUSED')
    parent=os.dup(root);fd=None
    try:
        for part in parts[:-1]:
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent)
            os.close(parent);parent=child
            info=os.fstat(parent)
            require(info.st_uid==owner and not info.st_mode&0o022,'CAPTURE_PARENT_REFUSED')
        fd=os.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=parent)
        before=os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_uid==owner and before.st_nlink==1
            and not before.st_mode&0o022 and 0<=before.st_size<=limit,'CAPTURE_FILE_REFUSED')
        with os.fdopen(fd,'rb',closefd=False) as stream:raw=stream.read(limit+1)
        after=os.fstat(fd)
        signature=lambda x:(x.st_dev,x.st_ino,x.st_size,x.st_mtime_ns,x.st_ctime_ns)
        require(len(raw)==before.st_size and signature(before)==signature(after),'CAPTURE_FILE_CHANGED')
        return raw
    finally:
        if fd is not None:os.close(fd)
        os.close(parent)

def write(path,raw):
    with path.open('xb') as output:
        output.write(raw);output.flush();os.fchmod(output.fileno(),0o400);os.fsync(output.fileno())

def capture(spool,destination,job,base_digest,base_policy,*,intake_uid,validator_policy,
            gate_path,observe,still_adopted):
    """`observe` and `still_adopted` belong to the protected controller.

    Call under the controller's deployment/adoption lock. A changed adopted base
    is rejected both before reading the intake result and before publication.
    Output is exclusive: a prior capture is never overwritten or implicitly used.
    """
    P=validator_policy
    require(type(job) is dict and set(job)=={'key','proposal','receipt','visible'},'CAPTURE_JOB_FIELDS')
    proposal=Q.checked(json.loads(job['proposal'],object_pairs_hook=P.pairs))
    require(Q.key(proposal)==job['key'] and proposal['draft'] is False,'CAPTURE_JOB_REFUSED')
    require(type(job['receipt']) is str and re.fullmatch('[0-9a-f]{64}',job['receipt']),'CAPTURE_RECEIPT_REFUSED')
    require(still_adopted(),'ADOPTED_BASE_CHANGED')
    identity=W.binding({'key':job['key'],'proposal':proposal},base_digest,base_policy)
    result_name=sha(encode(identity))
    destination=Path(destination);parent=directory(destination.parent,os.getuid())
    require(destination.name not in ('','.','..'),'CAPTURE_DESTINATION_REFUSED')
    root=None;created=False
    try:
        root=directory(Path(spool)/result_name,intake_uid)
        receipt_raw=read(root,'receipt.json',intake_uid,65536)
        require(sha(receipt_raw)==job['receipt'],'CAPTURE_RECEIPT_DIGEST')
        receipt=json.loads(receipt_raw,object_pairs_hook=P.pairs)
        require(type(receipt) is dict and set(receipt)==set(identity)|{'proposal_sha256','policy_sha256','deployment_authorized'}
            and all(receipt[k]==v for k,v in identity.items()) and receipt['deployment_authorized'] is False,
            'CAPTURE_RECEIPT_BINDING')
        for field in ('proposal_sha256','policy_sha256'):
            require(type(receipt[field]) is str and re.fullmatch('[0-9a-f]{64}',receipt[field]),'CAPTURE_RECEIPT_SHA')
        policy_raw=read(root,'policy.json',intake_uid,1024*1024)
        require(sha(policy_raw)==receipt['policy_sha256'],'CAPTURE_POLICY_DIGEST')
        proposed=P.checked_policy(json.loads(policy_raw,object_pairs_hook=P.pairs))
        manifest_raw=read(root,'source/manifest.json',intake_uid,4*1024**2)
        require(sha(manifest_raw)==receipt['proposal_sha256'],'CAPTURE_MANIFEST_DIGEST')
        manifest=json.loads(manifest_raw,object_pairs_hook=P.pairs)
        P.exact(manifest,('schema_version','rules_revision','files'))
        require(type(manifest['schema_version']) is int and manifest['schema_version']==1
            and manifest['rules_revision']==base_policy['rules_revision'],'CAPTURE_MANIFEST_RULES')
        files=manifest['files'];require(type(files) is list and 0<len(files)<=4096,'CAPTURE_FILE_LIMIT')
        names=set();directories=set();total=0
        for entry in files:
            P.exact(entry,('path','bytes','sha256'));name=P.relative(entry['path'])
            require(name not in names and name!='manifest.json','CAPTURE_DUPLICATE_PATH');names.add(name)
            require(type(entry['bytes']) is int and 0<=entry['bytes']<=32*1024**2
                and type(entry['sha256']) is str and re.fullmatch('[0-9a-f]{64}',entry['sha256']),'CAPTURE_FILE_FIELDS')
            total+=entry['bytes'];require(total<=32*1024**2,'CAPTURE_BYTE_LIMIT')
            directories.update(str(p) for p in PurePosixPath(name).parents if str(p)!='.')
            require(len(names)+len(directories)<=16384,'CAPTURE_NODE_LIMIT')
        require(not any(str(p) in names for name in names for p in PurePosixPath(name).parents if str(p)!='.'),'CAPTURE_PATH_COLLISION')
        os.mkdir(destination.name,0o700,dir_fd=parent);created=True
        source=destination/'source';source.mkdir(mode=0o700)
        for entry in files:
            raw=read(root,'source/'+entry['path'],intake_uid,entry['bytes'])
            require(len(raw)==entry['bytes'] and sha(raw)==entry['sha256'],'CAPTURE_SOURCE_DIGEST')
            path=source/entry['path'];path.parent.mkdir(parents=True,exist_ok=True,mode=0o700);write(path,raw)
        write(source/'manifest.json',manifest_raw);write(destination/'policy.json',policy_raw)
        # The fresh observation is not taken from any intake-controlled field
        # beyond the already allowlisted, exact PR identity.
        observed_binding=observe(proposal)
        observed={s['id']:observed_binding for s in base_policy['sources']
            if s['repository']=='MrJ-am/'+proposal['repository']}
        V.verify(source,base_policy,proposed,observed,receipt['proposal_sha256'],validator_policy=P,gate_path=gate_path)
        require(still_adopted(),'ADOPTED_BASE_CHANGED')
        result={'schema_version':1,'job_key':job['key'],'intake_receipt_sha256':job['receipt'],
            'base_sha256':base_digest,'base_policy_sha256':identity['base_policy_sha256'],
            'proposal_sha256':receipt['proposal_sha256'],'policy_sha256':receipt['policy_sha256'],
            'proposal':proposal,'observed':observed,'independently_verified':True,'deployment_authorized':False}
        write(destination/'capture.json',encode(result));W.persist_tree(destination);os.fsync(parent)
        return result
    except BaseException:
        if created:shutil.rmtree(destination);os.fsync(parent)
        raise
    finally:
        if root is not None:os.close(root)
        os.close(parent)
