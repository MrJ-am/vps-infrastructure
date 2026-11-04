"""Copy verified code artifacts under the collector's shared retention lock.

The protected caller resolves admission and selects roots. No production key,
application data, candidate command or archive extraction is involved.
"""
import fcntl,hashlib,json,os,shutil,stat
from pathlib import Path


def require(value):
    if not value:raise ValueError('DELIVERY_CAPTURE_REFUSED')


def directory(path,owner):
    parts=Path(path).parts
    require(parts[0]=='/' and '..' not in parts)
    fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)
    try:
        for part in parts[1:]:
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=fd)
            os.close(fd);fd=child
        info=os.fstat(fd)
        require(info.st_uid==owner and stat.S_IMODE(info.st_mode)==0o700)
        return fd
    except BaseException:os.close(fd);raise


def regular(parent,name,owner,maximum):
    fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=parent)
    try:
        info=os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid==owner and info.st_nlink==1
                and stat.S_IMODE(info.st_mode)==0o400 and 0<info.st_size<=maximum)
        return fd,info
    except BaseException:os.close(fd);raise


def unchanged(fd,before):
    after=os.fstat(fd)
    fields=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
    require(fields(before)==fields(after))


def read(parent,name,owner,maximum):
    fd,before=regular(parent,name,owner,maximum)
    try:
        raw=os.read(fd,maximum+1);require(len(raw)==before.st_size);unchanged(fd,before)
        return raw
    finally:os.close(fd)


def write(path,raw):
    with path.open('xb') as output:
        output.write(raw);output.flush();os.fchmod(output.fileno(),0o400);os.fsync(output.fileno())


def capture(proposal,policy,destination,*,attestations,cache,contract,verify):
    C=contract;C.text(proposal,C.HEX);C.policy(policy)
    destination=Path(destination)
    # Parent is an existing private control directory, never supplied by a PR.
    parent=directory(destination.parent,os.getuid())
    roots=[];lock=None;created=False
    try:
        att=directory(attestations,policy['requester_uid']);roots.append(att)
        raw=read(att,proposal+'.json',policy['requester_uid'],C.MAX_DOCUMENT)
        envelope=C.parse(raw);require(verify(envelope,policy))
        require(envelope['payload']['proposal_sha256']==proposal)
        root=directory(cache,policy['collector_uid']);roots.append(root)
        lock=os.open('.collection.lock',os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=root)
        info=os.fstat(lock)
        require(stat.S_ISREG(info.st_mode) and info.st_uid==policy['collector_uid']
                and info.st_nlink==1 and stat.S_IMODE(info.st_mode)==0o600)
        fcntl.flock(lock,fcntl.LOCK_SH|fcntl.LOCK_NB)
        selected=os.open(proposal,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=root);roots.append(selected)
        info=os.fstat(selected);require(info.st_uid==policy['collector_uid'] and stat.S_IMODE(info.st_mode)==0o700)
        receipt_raw=read(selected,'receipt.json',policy['collector_uid'],C.MAX_DOCUMENT)
        receipt=C.bound_receipt(C.parse(receipt_raw),proposal,policy['rules_revision'],policy['producer'])
        require(envelope['payload']['collector_receipt_sha256']==C.sha(C.canonical(receipt)))
        require(envelope['payload']['artifacts']==receipt['artifacts'])
        os.mkdir(destination.name,0o700,dir_fd=parent);created=True
        limits=dict(C.ARTIFACTS)
        for entry in receipt['artifacts']:
            name=entry['name'];fd,before=regular(selected,name,policy['collector_uid'],limits[name])
            try:
                require(before.st_size==entry['bytes'])
                hashed=hashlib.sha256();count=0
                with (destination/name).open('xb') as output:
                    while block:=os.read(fd,65536):
                        count+=len(block);require(count<=entry['bytes'])
                        hashed.update(block);output.write(block)
                    require(count==entry['bytes'] and hashed.hexdigest()==entry['sha256'])
                    unchanged(fd,before)
                    output.flush();os.fchmod(output.fileno(),0o400);os.fsync(output.fileno())
            finally:os.close(fd)
        write(destination/'attestation.json',raw)
        write(destination/'receipt.json',receipt_raw)
        result={'schema_version':1,'proposal_sha256':proposal,'attestation_sha256':C.sha(raw),
                'rules_revision':policy['rules_revision'],'artifacts':receipt['artifacts'],
                'signature_verified':True,'deployment_authorized':False}
        write(destination/'capture.json',C.canonical(result))
        fd=os.open(destination,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:os.fsync(fd)
        finally:os.close(fd)
        os.fsync(parent)
        return result
    except BaseException:
        if created:shutil.rmtree(destination);os.fsync(parent)
        raise
    finally:
        if lock is not None:os.close(lock)
        for fd in roots:os.close(fd)
        os.close(parent)
