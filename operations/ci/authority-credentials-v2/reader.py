"""Only the fixed signer credential on the qualified systemd ACL/RO mount."""
import os,stat,struct
from pathlib import Path
import contract as C

PATH='/run/credentials/mrjam-validation-authority.service/signing-key'

def acl(uid,permission):
    return struct.pack('<I',2)+b''.join(struct.pack('<HHI',tag,bits,identity) for tag,bits,identity in (
        (1,permission,0xffffffff),(2,permission,uid),(4,0,0xffffffff),(16,permission,0xffffffff),(32,0,0xffffffff)))

def read_key(path):
    C.require(str(path)==PATH and os.getuid()!=0,'SIGNING_CREDENTIAL_PATH_REFUSED')
    parent=descriptor=None
    try:
        for ancestor in ('/','/run','/run/credentials'):
            entry=os.lstat(ancestor)
            C.require(stat.S_ISDIR(entry.st_mode) and entry.st_uid==0 and entry.st_gid==0 and stat.S_IMODE(entry.st_mode)==0o755,'SIGNING_CREDENTIAL_ANCESTOR_REFUSED')
        parent=os.open(str(Path(PATH).parent),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
        directory=os.fstat(parent)
        C.require(directory.st_uid==0 and directory.st_gid==0 and stat.S_IMODE(directory.st_mode)==0o550
            and os.getxattr(parent,'system.posix_acl_access')==acl(os.getuid(),5)
            and os.fstatvfs(parent).f_flag&os.ST_RDONLY,'SIGNING_CREDENTIAL_DIRECTORY_REFUSED')
        descriptor=os.open('signing-key',os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=parent)
        before=os.fstat(descriptor)
        C.require(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_uid==0 and before.st_gid==0
            and stat.S_IMODE(before.st_mode)==0o440 and 0<before.st_size<=4096
            and os.getxattr(descriptor,'system.posix_acl_access')==acl(os.getuid(),4)
            and os.fstatvfs(descriptor).f_flag&os.ST_RDONLY,'SIGNING_CREDENTIAL_FILE_REFUSED')
        raw=os.read(descriptor,4097);after=os.fstat(descriptor)
        C.require(len(raw)==before.st_size and (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)==(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns),'SIGNING_CREDENTIAL_CHANGED')
        return raw
    except C.Refused:raise
    except (OSError,ValueError):raise C.Refused('SIGNING_CREDENTIAL_UNAVAILABLE') from None
    finally:C.close_fds([fd for fd in (descriptor,parent) if fd is not None])
