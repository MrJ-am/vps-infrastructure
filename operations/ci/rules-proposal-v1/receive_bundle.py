"""Receive only the sealed private proposal; no Git/API/Nix/service operation."""
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import signal
import stat
import sys

PACKAGE = "/nix/store/1j61zvqin8df0vdazsdxlfssf5rdc54z-mrjam-rules-bootstrap-proposal-1"
DIRECTORY = Path("/var/lib/mrjam-ci-rules-proposal")
STATE = Path("/var/lib/mrjam-cutover/first-deployment")
BYTES = 874
SHA256 = "9938901b832d40e20992bf2063a79f19fed1fe37b4a6d4eb36bb2842e369c975"
OWNER = (0, 0)
FINAL = "proposal.bundle"
PENDING = ".proposal.bundle.next"


class Refused(RuntimeError):
    pass


def require(value):
    if not value:
        raise Refused("RULES_PROPOSAL_BUNDLE_REFUSED")


def protected_directory(path, create=False):
    """Same traversal as qualified receive_postrelease_code.py."""
    descriptor=os.open("/",os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        for part in Path(path).parts[1:]:
            if create:
                try:
                    os.mkdir(part,0o700,dir_fd=descriptor)
                    os.fsync(descriptor)
                except FileExistsError:
                    pass
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=descriptor)
            os.close(descriptor);descriptor=child
            item=os.fstat(descriptor)
            require(item.st_uid==0 and not stat.S_IMODE(item.st_mode)&0o022)
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def inspect(directory, name, raw):
    try:
        fd=os.open(name,os.O_RDONLY|os.O_NONBLOCK|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=directory)
    except FileNotFoundError:
        return None
    try:
        before=os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and (before.st_uid,before.st_gid)==OWNER
                and stat.S_IMODE(before.st_mode)==0o600 and before.st_nlink in (1,2)
                and 0 <= before.st_size <= BYTES)
        contents=os.read(fd,BYTES+1)
        after=os.fstat(fd)
        require((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)
                == (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns)
                and len(contents)==before.st_size and raw.startswith(contents))
        return before
    finally:
        os.close(fd)


def publish(directory, raw):
    require(type(raw) is bytes and len(raw)==BYTES and hashlib.sha256(raw).hexdigest()==SHA256)
    target=inspect(directory,FINAL,raw)
    pending=inspect(directory,PENDING,raw)
    if target is not None:
        require(target.st_size==BYTES)
        if pending is None:
            require(target.st_nlink==1)
        else:
            require(target.st_nlink==pending.st_nlink==2 and pending.st_size==BYTES
                    and (target.st_dev,target.st_ino)==(pending.st_dev,pending.st_ino))
            os.unlink(PENDING,dir_fd=directory);os.fsync(directory)
        return False
    if pending is None:
        fd=os.open(PENDING,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=directory)
        start=0
    else:
        require(pending.st_nlink==1)
        fd=os.open(PENDING,os.O_WRONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=directory)
        reopened=os.fstat(fd)
        require((reopened.st_dev,reopened.st_ino)==(pending.st_dev,pending.st_ino))
        start=pending.st_size
    try:
        os.lseek(fd,start,os.SEEK_SET)
        while start<len(raw):
            written=os.write(fd,raw[start:]);require(written>0);start+=written
        os.fsync(fd)
    finally:
        os.close(fd)
    checked=inspect(directory,PENDING,raw)
    require(checked is not None and checked.st_size==BYTES and checked.st_nlink==1)
    os.link(PENDING,FINAL,src_dir_fd=directory,dst_dir_fd=directory,follow_symlinks=False)
    os.fsync(directory)
    os.unlink(PENDING,dir_fd=directory)
    os.fsync(directory)
    return True


def main():
    if len(sys.argv)!=1 or os.geteuid()!=0 or os.uname().nodename!='srv1982677':
        return 64
    resource.setrlimit(resource.RLIMIT_CORE,(0,0));os.umask(0o077)
    def interrupted(*_):raise Refused("RULES_PROPOSAL_BUNDLE_REFUSED")
    saved={n:signal.signal(n,interrupted) for n in (signal.SIGALRM,signal.SIGTERM,signal.SIGINT)}
    signal.alarm(30)
    state=lock=directory=None
    try:
        sys.path.insert(0,PACKAGE+'/libexec')
        import entry
        spec=importlib.util.spec_from_file_location('qualified_bootstrap',entry.BOOTSTRAP)
        bootstrap=importlib.util.module_from_spec(spec);spec.loader.exec_module(bootstrap)
        state=protected_directory(STATE)
        lock=os.open('transaction.lock',os.O_RDWR|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=state)
        info=os.fstat(lock)
        require(stat.S_ISREG(info.st_mode) and (info.st_uid,info.st_gid)==OWNER
                and stat.S_IMODE(info.st_mode)==0o600 and info.st_nlink==1)
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        entry.gate(bootstrap)
        raw=sys.stdin.buffer.read(BYTES+1)
        require(len(raw)==BYTES and hashlib.sha256(raw).hexdigest()==SHA256)
        directory=protected_directory(DIRECTORY,create=True)
        info=os.fstat(directory)
        require((info.st_uid,info.st_gid)==OWNER and stat.S_IMODE(info.st_mode)==0o700)
        created=publish(directory,raw)
        entry.gate(bootstrap)
        print(json.dumps({'schema_version':1,'code':'RULES_PROPOSAL_BUNDLE_RECEIVED',
            'created':created,'bytes':BYTES,'sha256':SHA256,'proposal_opened':False},sort_keys=True))
        return 0
    except Exception:
        print('{"schema_version":1,"code":"RULES_PROPOSAL_BUNDLE_REFUSED"}')
        return 1
    finally:
        for fd in (directory,lock,state):
            if fd is not None:os.close(fd)
        signal.alarm(0)
        for n,handler in saved.items():signal.signal(n,handler)


if __name__=='__main__':
    raise SystemExit(main())
