"""One administrative credential import; stdin is never echoed or logged."""
import base64,hashlib,json,os,re,ssl,stat,subprocess,sys,time,urllib.request
from pathlib import Path
OPENSSL='/nix/store/fya253x5ky7rhfz6rkgdwjr1fzf7fy71-openssl-3.6.5-bin/bin/openssl'
DIRECTORY=Path('/var/lib/mrjam-github-app')
PERMISSIONS={'contents':'write','pull_requests':'write','statuses':'write','workflows':'write','metadata':'read'}
class Refused(Exception):pass
def require(value,code):
    if not value:raise Refused(code)
def encoded(raw):return base64.urlsafe_b64encode(raw).rstrip(b'=')
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode()
def checked(value):
    require(type(value) is dict and set(value)=={'app_id','owner_id','slug','private_key','permissions'},'FIELDS_REFUSED')
    require(type(value['app_id']) is int and 0<value['app_id']<2**53 and value['owner_id']==12571490,'IDENTITY_REFUSED')
    require(type(value['slug']) is str and re.fullmatch('[a-z0-9][a-z0-9-]{0,99}',value['slug']),'SLUG_REFUSED')
    require(value['permissions']==PERMISSIONS,'PERMISSIONS_REFUSED')
    require(type(value['private_key']) is str and value['private_key'].isascii() and 1000<len(value['private_key'])<16384,'KEY_REFUSED')
    return value
def jwt(value):
    checked(value);now=int(time.time())
    message=encoded(canonical({'alg':'RS256','typ':'JWT'}))+b'.'+encoded(canonical({'iat':now-60,'exp':now+540,'iss':value['app_id']}))
    fd=os.memfd_create('github-app-private-key',os.MFD_CLOEXEC)
    try:
        raw=value['private_key'].encode();offset=0
        while offset<len(raw):offset+=os.write(fd,raw[offset:])
        result=subprocess.run([OPENSSL,'dgst','-sha256','-sign','/proc/self/fd/'+str(fd)],input=message,
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,pass_fds=(fd,),timeout=10,env={'PATH':'/nonexistent','LANG':'C'})
        require(result.returncode==0 and 256<=len(result.stdout)<=1024,'KEY_SIGNATURE_REFUSED')
        return (message+b'.'+encoded(result.stdout)).decode()
    finally:os.close(fd)
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None
def identity(value):
    request=urllib.request.Request('https://api.github.com/app',headers={
        'Authorization':'Bearer '+jwt(value),'Accept':'application/vnd.github+json',
        'User-Agent':'mrjam-github-app-import','X-GitHub-Api-Version':'2022-11-28'})
    tls=ssl.create_default_context(cafile='/etc/ssl/certs/ca-certificates.crt')
    with urllib.request.build_opener(NoRedirect,urllib.request.HTTPSHandler(context=tls)).open(request,timeout=20) as response:
        require(response.status==200,'APP_AUTH_REFUSED');raw=response.read(131073)
        require(len(raw)<=131072,'RESPONSE_LIMIT')
    observed=json.loads(raw)
    require(observed.get('id')==value['app_id'] and observed.get('slug')==value['slug']
            and observed.get('owner',{}).get('id')==12571490
            and observed.get('owner',{}).get('login')=='MrJ-am','LIVE_IDENTITY_REFUSED')
    require(observed.get('permissions')==PERMISSIONS and observed.get('events')==[],'LIVE_PERMISSIONS_REFUSED')
def install(directory,value):
    checked(value);directory.mkdir(mode=0o700,exist_ok=True)
    info=directory.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid==os.getuid()
            and stat.S_IMODE(info.st_mode)==0o700,'DIRECTORY_REFUSED')
    # Never replace a registered identity or silently rotate its key.
    fd=os.open(directory/'app-credentials.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
    with os.fdopen(fd,'wb') as stream:
        stream.write(canonical(value));stream.flush();os.fsync(stream.fileno())
    fd=os.open(directory,os.O_DIRECTORY|os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)
def main():
    require(os.getuid()==0 and len(sys.argv)==1,'ADMIN_REQUIRED')
    raw=sys.stdin.buffer.read(32769);require(0<len(raw)<=32768,'INPUT_LIMIT')
    def pairs(items):
        result={}
        for key,value in items:
            require(key not in result,'DUPLICATE_FIELD');result[key]=value
        return result
    value=checked(json.loads(raw,object_pairs_hook=pairs))
    require(not (DIRECTORY/'app-credentials.json').exists(),'IDENTITY_ALREADY_INSTALLED')
    identity(value);install(DIRECTORY,value)
    print(json.dumps({'code':'APP_IDENTITY_INSTALLED','app_id':value['app_id'],'slug':value['slug'],
                      'installation_verified':False,'pipeline_activated':False}))
if __name__=='__main__':
    try:main()
    except Exception:
        print('{"code":"APP_IDENTITY_IMPORT_REFUSED"}');raise SystemExit(1) from None
