"""Read-only export of an already collected result; no compiler or signer here."""
from __future__ import annotations
import fcntl,hashlib,os,socket,stat,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import contract as C
import admission_control as R
import collector as S

POLICY_PATH='@admission-export-anchor@'
ARTIFACT_ROOT='/var/lib/mrjam-validation-collector/authority-v1/artifacts'

def export_policy(value):
    C.exact(value,{'schema_version','rules_revision','requester_uid','producer'})
    C.require(type(value['schema_version']) is int and value['schema_version']==1)
    C.text(value['rules_revision'],C.REV);C.integer(value['requester_uid'],1,2**31-1)
    C.producer_binding(value['producer']);C.require(value['rules_revision']==value['producer']['rules_revision'],'PRODUCER_RULES_REFUSED')
    return value

def open_directory(path):
    parts=Path(path).parts;C.require(parts[0]=='/' and '..' not in parts,'CACHE_PATH_REFUSED')
    fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)
    try:
        for part in parts[1:]:
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=fd);os.close(fd);fd=child
        info=os.fstat(fd);C.require(info.st_uid==os.getuid() and stat.S_IMODE(info.st_mode)==0o700,'CACHE_METADATA_REFUSED')
        return fd
    except BaseException:os.close(fd);raise

def collect(root,proposal,rules,end):
    fds=[];lock=directory=None
    try:
        lock=os.open('.collection.lock',os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=root)
        info=os.fstat(lock);C.require(stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and info.st_nlink==1 and stat.S_IMODE(info.st_mode)==0o600,'CACHE_LOCK_REFUSED')
        fcntl.flock(lock,fcntl.LOCK_SH|fcntl.LOCK_NB)
        receipt=S.cached(root,proposal,rules)
        directory=os.open(proposal,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=root)
        for entry in receipt['artifacts']:
            C.require(time.monotonic()<end,'EXPORT_TIMEOUT')
            source=os.open(entry['name'],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=directory)
            target=os.memfd_create('mrjam-collected-code',os.MFD_CLOEXEC|os.MFD_ALLOW_SEALING)
            fds.append(target)
            try:
                before=os.fstat(source)
                C.require(stat.S_ISREG(before.st_mode) and before.st_uid==os.getuid() and before.st_nlink==1 and stat.S_IMODE(before.st_mode)==0o400 and before.st_size==entry['bytes'],'ARTIFACT_METADATA_REFUSED')
                size=0;hashed=hashlib.sha256()
                while size<entry['bytes']:
                    C.require(time.monotonic()<end,'EXPORT_TIMEOUT')
                    block=os.read(source,min(65536,entry['bytes']-size));C.require(block,'ARTIFACT_TRUNCATED');size+=len(block);hashed.update(block)
                    view=memoryview(block)
                    while view:
                        written=os.write(target,view);C.require(written>0,'EXPORT_WRITE_REFUSED');view=view[written:]
                after=os.fstat(source)
                C.require(os.read(source,1)==b'' and (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)==(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns),'ARTIFACT_CHANGED')
                C.require(hashed.hexdigest()==entry['sha256'],'ARTIFACT_HASH_REFUSED')
                fcntl.fcntl(target,fcntl.F_ADD_SEALS,C.SEALS);os.lseek(target,0,os.SEEK_SET)
            finally:os.close(source)
        return receipt,fds
    except BaseException:C.close_fds(fds);raise
    finally:
        if directory is not None:os.close(directory)
        if lock is not None:os.close(lock)

def serve(connection,value,root_path,*,budget=10):
    end=time.monotonic()+budget;fds=[];root=None
    try:
        export_policy(value)
        S.EXPECTED_BINDING=value['producer']
        C.require(C.peer_uid(connection)==value['requester_uid'],'EXPORT_PEER_REFUSED')
        proposal=C.request(connection,end=end)
        value=R.export_policy(proposal)
        export_policy(value)
        S.EXPECTED_BINDING=value['producer']
        root=open_directory(root_path)
        receipt,fds=collect(root,proposal,value['rules_revision'],end)
        raw=C.canonical(receipt);C.require(len(raw)<=C.MAX_RECEIPT,'RECEIPT_LIMIT')
        C.send_packet(connection,raw,fds,end=end)
        return True
    except BaseException:
        try:C.send_packet(connection,b'{"code":"COLLECTOR_EXPORT_REFUSED","schema_version":1}',[],end=end)
        except BaseException:pass
        return False
    finally:
        C.close_fds(fds)
        if root is not None:os.close(root)

def main():
    try:
        C.require(len(sys.argv)==1 and os.getuid()!=0,'INVOCATION_REFUSED')
        # Store files may be hardlink-deduplicated; only immutable root ownership
        # and the closed content are authority here, never a caller-selected path.
        path=Path(POLICY_PATH);C.require(str(path).startswith('/nix/store/'),'POLICY_PATH_REFUSED')
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
        with os.fdopen(fd,'rb') as stream:
            meta=os.fstat(stream.fileno());C.require(stat.S_ISREG(meta.st_mode) and meta.st_uid==0 and not meta.st_mode&0o222 and 0<meta.st_size<=4096,'POLICY_METADATA_REFUSED');value=C.parse(stream.read(4097),4096)
        with socket.socket(fileno=os.dup(0)) as connection:return 0 if serve(connection,value,ARTIFACT_ROOT) else 1
    except BaseException:return 1
if __name__=='__main__':raise SystemExit(main())
