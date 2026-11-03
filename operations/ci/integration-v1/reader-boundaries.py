"""Invented credential views, exact packaged reader, private mount namespaces."""
import json,os,pwd,stat,struct,subprocess,sys
from pathlib import Path
sys.path.insert(0,'@authority@/lib')
import contract as C
import signing_credential as K

STATE=Path('/var/lib/mrjam-invented-reader')
VIEW=STATE/'view'
KEY=VIEW/'signing-key'
UID=61002
MOUNT='@mount@'
UNSHARE='@unshare@'
PYTHON='@python@'

def require(value,code):
    if not value:raise RuntimeError(code)

def run(args):
    result=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10,check=False)
    require(result.returncode==0,'SYNTHETIC_MOUNT_REFUSED')

def child(readonly):
    # A new mount namespace prevents systemd's automatic hiding of another
    # unit's credential directory from obscuring the reader's negative tests.
    run([MOUNT,'-t','tmpfs','-o','mode=0755','tmpfs','/run/credentials'])
    target=Path(K.PATH).parent;target.mkdir(mode=0o755)
    run([MOUNT,'--bind',str(VIEW),str(target)])
    if readonly:run([MOUNT,'-o','remount,bind,ro',str(target)])
    account=pwd.getpwnam('invented-signer')
    os.setgroups([]);os.setgid(account.pw_gid);os.setuid(account.pw_uid)
    observed_readonly=bool(os.statvfs(K.PATH).f_flag&os.ST_RDONLY)
    try:
        K.read_key(K.PATH);accepted=True;code='ACCEPTED'
    except C.Refused as failure:
        accepted=False;code=str(failure)
    print(json.dumps({'accepted':accepted,'readonly':observed_readonly,'uid':os.getuid(),'code':code},sort_keys=True))

def main():
    require(os.getuid()==0 and Path('/etc/mrjam-reader-fixture').read_text()=='INVENTED_VM_ONLY\n','NOT_SYNTHETIC_VM')
    if len(sys.argv)==2 and sys.argv[1] in ('ro','rw'):
        child(sys.argv[1]=='ro');return
    require(len(sys.argv)==1 and not STATE.exists(),'FIXTURE_ARGUMENTS_REFUSED')
    STATE.mkdir(mode=0o700);VIEW.mkdir(mode=0o700)
    Path('/run/credentials').mkdir(mode=0o755,exist_ok=True)
    checks=[]
    def baseline():
        KEY.unlink(missing_ok=True)
        KEY.write_bytes(b'INVENTED NONSECRET CREDENTIAL\n');KEY.chmod(0o400)
        os.setxattr(VIEW,'system.posix_acl_access',K.acl(UID,5))
        os.setxattr(KEY,'system.posix_acl_access',K.acl(UID,4))
    def probe(name,*,accepted=False,readonly=True):
        result=subprocess.run([UNSHARE,'--mount','--propagation','private',PYTHON,'-I','-S',__file__,'ro' if readonly else 'rw'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10,check=False)
        require(result.returncode==0 and not result.stderr and len(result.stdout)<=1024,'READER_PROBE_EXECUTION_REFUSED')
        observed=json.loads(result.stdout)
        require(set(observed)=={'accepted','readonly','uid','code'} and observed['accepted']==accepted and observed['readonly']==readonly and observed['uid']==UID,'READER_BOUNDARY_MISMATCH')
        require((observed['code']=='ACCEPTED')==accepted,'READER_RESULT_CODE_MISMATCH')
        checks.append({'case':name,'accepted':accepted,'readonly':readonly,'code':observed['code']})
    baseline();probe('exact-acl-readonly',accepted=True)
    KEY.chmod(0o640);probe('wrong-file-mode')
    baseline();raw=K.acl(UID,4)
    os.setxattr(KEY,'system.posix_acl_access',raw[:20]+struct.pack('<HHI',2,4,61006)+raw[20:]);probe('extra-user-acl')
    baseline();os.setxattr(KEY,'system.posix_acl_access',K.acl(61003,4));probe('wrong-user-acl')
    baseline();raw=K.acl(UID,5)
    os.setxattr(VIEW,'system.posix_acl_access',raw[:20]+struct.pack('<HHI',2,5,61006)+raw[20:]);probe('extra-parent-acl')
    baseline();alias=STATE/'alias';os.link(KEY,alias)
    try:probe('hardlink')
    finally:alias.unlink()
    baseline();KEY.chmod(0o600);KEY.write_bytes(b'X'*4097);os.setxattr(KEY,'system.posix_acl_access',K.acl(UID,4));probe('oversize')
    baseline();probe('writable-mount',readonly=False)
    baseline();probe('final-exact-acl-readonly',accepted=True)
    print(json.dumps({'schema_version':1,'checks':checks,'production_access':False,'scope':'exact-packaged-reader-private-kernel-mount-namespace-dropped-uid'},sort_keys=True))

if __name__=='__main__':main()
