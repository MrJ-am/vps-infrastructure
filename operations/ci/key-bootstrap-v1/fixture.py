"""Only a disposable VM uses this test's synthetic keys and mutations."""
import base64,hashlib,json,os,stat,subprocess,sys
from pathlib import Path
sys.path.insert(0,'@package@/lib')
import bootstrap as B
BIN='@package@/bin/mrjam-validation-authority-key-bootstrap'
OPENSSL='@openssl@'
RUNUSER='@runuser@'
KEY=Path('/var/lib/mrjam-validation-authority/signing-key')
DIR=KEY.parent
STATE=Path('/var/lib/mrjam-bootstrap-invented-tests')
def require(value):
    if not value:raise RuntimeError('SYNTHETIC_KEY_BOOTSTRAP_CHECK_REFUSED')
def run(args):return subprocess.run(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30,check=False)
def invoke(*,success,args=(),user=None):
    command=[BIN,*args]
    if user:command=[RUNUSER,'-u',user,'--',*command]
    result=run(command)
    require((result.returncode==0)==success and not result.stderr and len(result.stdout)<=1024 and b'PRIVATE KEY' not in result.stdout)
    value=json.loads(result.stdout)
    require(value.get('schema_version')==1)
    if not success:require(set(value)=={'schema_version','code'} and value['code'].startswith('AUTHORITY_KEY_'))
    return value
def main():
    require(os.getuid()==0 and Path('/etc/mrjam-key-fixture').read_text()=='INVENTED_VM_ONLY\n' and not DIR.exists())
    checks=[];STATE.mkdir(mode=0o700)
    invoke(success=False,args=('--path','/tmp/forbidden'));invoke(success=False,user='invented-outsider');require(not DIR.exists());checks.append('root-and-no-arguments')
    first=invoke(success=True);require(first['code']=='AUTHORITY_KEY_CREATED')
    require(set(first)=={'schema_version','code','public_key_der','key_id','private_key_exported','ci_activated'} and first['private_key_exported'] is False and first['ci_activated'] is False)
    public=base64.b64decode(first['public_key_der'],validate=True);require(len(public)==44 and public.startswith(B.PUBLIC_PREFIX) and hashlib.sha256(public).hexdigest()==first['key_id'])
    meta=KEY.stat();require(meta.st_uid==meta.st_gid==0 and stat.S_IMODE(meta.st_mode)==0o400 and meta.st_nlink==1 and stat.S_IMODE(DIR.stat().st_mode)==0o700);checks.append('create-private-export-public-only')
    # A read may update atime after the publication rename changed ctime.
    # Inode, ownership, mode, links, size and modification/change times remain.
    same=lambda value:tuple(getattr(value,name) for name in ('st_dev','st_ino','st_uid','st_gid','st_mode','st_nlink','st_size','st_mtime_ns','st_ctime_ns'))
    second=invoke(success=True);require(second==dict(first,code='AUTHORITY_KEY_ALREADY_PRESENT') and same(KEY.stat())==same(meta));checks.append('repeat-preserves-existing-key')
    require(run([RUNUSER,'-u','invented-outsider','--','@python@','-I','-S','-c','open("'+str(KEY)+'","rb")']).returncode!=0);checks.append('nonroot-cannot-read-key')
    (STATE/'public.der').write_bytes(public);(STATE/'message').write_bytes(b'INVENTED QUALIFICATION MESSAGE\n')
    require(run([OPENSSL,'pkeyutl','-sign','-rawin','-inkey',str(KEY),'-in',str(STATE/'message'),'-out',str(STATE/'signature')]).returncode==0)
    require(run([OPENSSL,'pkeyutl','-verify','-rawin','-pubin','-keyform','DER','-inkey',str(STATE/'public.der'),'-in',str(STATE/'message'),'-sigfile',str(STATE/'signature')]).returncode==0);checks.append('actual-ed25519-signature')
    KEY.chmod(0o440);invoke(success=False);KEY.chmod(0o400)
    DIR.chmod(0o750);invoke(success=False);DIR.chmod(0o700)
    os.link(KEY,STATE/'alias');invoke(success=False);(STATE/'alias').unlink();checks.append('metadata-and-hardlink-refused')
    backup=STATE/'saved-key';KEY.rename(backup);KEY.symlink_to(backup);invoke(success=False);KEY.unlink();backup.rename(KEY)
    moved=STATE/'saved-directory';DIR.rename(moved);DIR.symlink_to(moved);invoke(success=False);DIR.unlink();moved.rename(DIR);checks.append('file-and-directory-symlink-refused')
    pending=DIR/'signing-key.next';pending.write_bytes(b'INVENTED ABANDONED STATE');pending.chmod(0o400);invoke(success=False);require(pending.exists());pending.unlink();checks.append('stale-staging-refused-without-deletion')
    pending.write_bytes(b'INVENTED COLLISION');parent=os.open(DIR,os.O_RDONLY|os.O_DIRECTORY)
    try:
        try:B.rename_no_replace(parent)
        except B.Refused:pass
        else:raise RuntimeError('SYNTHETIC_RENAME_REPLACED_KEY')
        require(KEY.stat().st_ino==meta.st_ino and pending.exists())
    finally:os.close(parent);pending.unlink()
    checks.append('kernel-no-replacement-publication')
    KEY.rename(backup)
    require(run([OPENSSL,'genpkey','-algorithm','X25519','-out',str(KEY)]).returncode==0);KEY.chmod(0o400)
    invoke(success=False);KEY.unlink();backup.rename(KEY);checks.append('non-ed25519-key-refused')
    require(invoke(success=True)['key_id']==first['key_id']);require(not pending.exists())
    print(json.dumps({'schema_version':1,'checks':checks,'production_access':False,'private_key_exported':False,'ci_activated':False},sort_keys=True))
if __name__=='__main__':main()
