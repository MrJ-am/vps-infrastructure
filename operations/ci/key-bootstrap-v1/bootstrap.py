"""Create once a local root-only Ed25519 key; release its public DER only."""
import base64,ctypes,fcntl,hashlib,json,os,socket,stat,subprocess,sys

OPENSSL='@openssl@'
HOST='srv1982677'
DIRECTORY='mrjam-validation-authority'
FINAL='signing-key'
STAGING='signing-key.next'
PUBLIC_PREFIX=bytes.fromhex('302a300506032b6570032100')

class Refused(Exception):pass
def require(condition,code='AUTHORITY_KEY_BOOTSTRAP_REFUSED'):
    if not condition:raise Refused(code)
def metadata(fd,mode,*,directory=False):
    observed=os.fstat(fd)
    require((stat.S_ISDIR if directory else stat.S_ISREG)(observed.st_mode)
        and observed.st_uid==0 and observed.st_gid==0 and stat.S_IMODE(observed.st_mode)==mode,'AUTHORITY_KEY_METADATA_REFUSED')
    require(not {'system.posix_acl_access','system.posix_acl_default'}.intersection(os.listxattr(fd)),'AUTHORITY_KEY_ACL_REFUSED')
    if not directory:require(observed.st_nlink==1 and 0<observed.st_size<=4096,'AUTHORITY_KEY_METADATA_REFUSED')
    return observed
def command(args,fds):
    result=subprocess.run([OPENSSL,*args],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
        pass_fds=tuple(fds),env={'LANG':'C','LC_ALL':'C','OPENSSL_CONF':'/dev/null'},timeout=10,check=False)
    require(result.returncode==0,'AUTHORITY_KEY_CRYPTO_REFUSED')
def public_key(fd):
    # The private file is never read into Python or sent through a pipe.
    before=metadata(fd,0o400)
    public=os.memfd_create('mrjam-public-ed25519',os.MFD_CLOEXEC)
    try:
        command(['pkey','-in','/proc/self/fd/'+str(fd),'-check','-noout'],[fd])
        command(['pkey','-in','/proc/self/fd/'+str(fd),'-pubout','-outform','DER','-out','/proc/self/fd/'+str(public)],[fd,public])
        require(os.fstat(public).st_size==44,'AUTHORITY_KEY_TYPE_REFUSED')
        raw=os.pread(public,45,0)
        require(len(raw)==44 and raw.startswith(PUBLIC_PREFIX),'AUTHORITY_KEY_TYPE_REFUSED')
        after=metadata(fd,0o400)
        require((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)==
                (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns),'AUTHORITY_KEY_CHANGED')
        return raw
    finally:os.close(public)
def rename_no_replace(parent):
    libc=ctypes.CDLL(None,use_errno=True)
    rename=libc.renameat2
    rename.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint]
    rename.restype=ctypes.c_int
    require(rename(parent,STAGING.encode(),parent,FINAL.encode(),1)==0,'AUTHORITY_KEY_PUBLICATION_REFUSED')
def execute():
    require(len(sys.argv)==1 and os.getuid()==0 and os.geteuid()==0 and os.getgid()==0 and socket.gethostname()==HOST,'AUTHORITY_KEY_CONTEXT_REFUSED')
    os.umask(0o077)
    descriptors=[];parent=None;key=None;created=False;published=False
    try:
        current=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC);descriptors.append(current)
        metadata(current,0o755,directory=True)
        for name in ('var','lib'):
            current=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=current);descriptors.append(current)
            metadata(current,0o755,directory=True)
        try:os.mkdir(DIRECTORY,0o700,dir_fd=current);os.fsync(current)
        except FileExistsError:pass
        parent=os.open(DIRECTORY,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=current);descriptors.append(parent)
        metadata(parent,0o700,directory=True)
        fcntl.flock(parent,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:os.stat(STAGING,dir_fd=parent,follow_symlinks=False)
        except FileNotFoundError:pass
        else:raise Refused('AUTHORITY_KEY_STAGING_PRESENT')
        try:key=os.open(FINAL,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=parent)
        except FileNotFoundError:
            key=os.open(STAGING,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=parent);created=True
            command(['genpkey','-algorithm','ED25519','-out','/proc/self/fd/'+str(key)],[key])
            os.fchmod(key,0o400);os.fsync(key)
            raw=public_key(key)
            rename_no_replace(parent);published=True;os.fsync(parent)
        else:raw=public_key(key)
        return {'schema_version':1,'code':'AUTHORITY_KEY_CREATED' if created else 'AUTHORITY_KEY_ALREADY_PRESENT',
            'public_key_der':base64.b64encode(raw).decode('ascii'),'key_id':hashlib.sha256(raw).hexdigest(),
            'private_key_exported':False,'ci_activated':False}
    finally:
        if created and not published and parent is not None and key is not None:
            try:
                observed=os.stat(STAGING,dir_fd=parent,follow_symlinks=False);opened=os.fstat(key)
                if (observed.st_dev,observed.st_ino)==(opened.st_dev,opened.st_ino):os.unlink(STAGING,dir_fd=parent);os.fsync(parent)
            except OSError:pass
        if key is not None:os.close(key)
        for fd in reversed(descriptors):os.close(fd)
def main():
    try:result=execute();status=0
    except Refused as failure:result={'schema_version':1,'code':str(failure)};status=1
    except BaseException:result={'schema_version':1,'code':'AUTHORITY_KEY_BOOTSTRAP_REFUSED'};status=1
    print(json.dumps(result,sort_keys=True,separators=(',',':')),flush=True)
    return status
if __name__=='__main__':raise SystemExit(main())
