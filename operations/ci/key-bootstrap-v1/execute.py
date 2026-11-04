"""Execute the reviewed fixed key bootstrap on the observed generation only."""
import base64,fcntl,hashlib,json,os,stat,subprocess,sys
CURRENT='/nix/store/phi68cwg38madbq8p805yvrsyry8g8wr-nixos-system-srv1982677-26.05pre-git'
PACKAGE='/nix/store/5mljdc68ab1siz9w0ckwmnjfn6969hqa-mrjam-validation-authority-key-bootstrap-1'
SOURCE_SHA='fadd497d30dc425ca1479cf6e3ab934437bfd8213638189852ca7c917bc95306'
def require(value):
    if not value:raise RuntimeError()
def execute():
    require(len(sys.argv)==1 and os.geteuid()==os.getegid()==0 and os.uname().nodename=='srv1982677')
    fd=os.open('/var/lib/mrjam-cutover/first-deployment/transaction.lock',os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        s=os.fstat(fd);require(stat.S_ISREG(s.st_mode) and s.st_uid==s.st_gid==0 and stat.S_IMODE(s.st_mode)==0o600 and s.st_nlink==1)
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        require(all(os.path.realpath(p)==CURRENT for p in ('/run/current-system','/nix/var/nix/profiles/system')))
        env={'LANG':'C','LC_ALL':'C','NIX_PATH':''}
        verify=subprocess.run([CURRENT+'/sw/bin/nix-store','--verify-path',PACKAGE],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,env=env,timeout=30)
        require(verify.returncode==0)
        with open(PACKAGE+'/lib/bootstrap.py','rb') as f:require(hashlib.file_digest(f,'sha256').hexdigest()==SOURCE_SHA)
        result=subprocess.run([PACKAGE+'/bin/mrjam-validation-authority-key-bootstrap'],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env=env,timeout=45)
        require(result.returncode==0 and len(result.stdout)<=2048)
        value=json.loads(result.stdout)
        require(set(value)=={'schema_version','code','public_key_der','key_id','private_key_exported','ci_activated'})
        require(type(value['schema_version']) is int and value['schema_version']==1 and value['code'] in ('AUTHORITY_KEY_CREATED','AUTHORITY_KEY_ALREADY_PRESENT'))
        require(value['private_key_exported'] is False and value['ci_activated'] is False)
        public=base64.b64decode(value['public_key_der'],validate=True)
        require(len(public)==44 and public.startswith(bytes.fromhex('302a300506032b6570032100')) and hashlib.sha256(public).hexdigest()==value['key_id'])
        return value
    finally:os.close(fd)
if __name__=='__main__':
    try:value=execute()
    except BaseException:
        print('{"schema_version":1,"code":"AUTHORITY_KEY_EXECUTION_REFUSED"}');sys.exit(1)
    print(json.dumps(value,sort_keys=True,separators=(',',':')))
