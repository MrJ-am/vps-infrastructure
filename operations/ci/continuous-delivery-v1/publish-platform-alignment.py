"""Fixed private candidate branch publication; no main update or deployment."""
import base64,hashlib,json,os,stat,subprocess,sys
from pathlib import Path
from urllib.error import HTTPError
sys.path.insert(0,'/nix/store/adylyavm0s2y1zjrcpmg0zyklhg3p89d-mrjam-github-proposal-discovery-1/lib')
import github_proposals as P

HEAD='5a05461e9e3eb7cf77e99b85ae8d49630f13004d'
BASE='6009020151cdd6e069aed67b4970b3b6de1b5151'
BRANCH='spectre/source-alignment-20261103'
GIT='/run/current-system/sw/bin/git'
ROOT=Path('/var/lib/mrjam-github-intake-bootstrap')

def require(value,code):
    if not value:raise RuntimeError(code)

def run(args,env):
    result=subprocess.run([GIT,*args],env=env,stdin=subprocess.DEVNULL,
                          stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=120)
    require(result.returncode==0,'GIT_OPERATION_FAILED')

def main():
    require(os.getuid()==0,'ADMIN_REQUIRED')
    info=ROOT.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid==0 and stat.S_IMODE(info.st_mode)==0o700,'SPOOL_REFUSED')
    bundle=ROOT/'platform-5a05461.bundle'
    require(not bundle.is_symlink() and hashlib.sha256(bundle.read_bytes()).hexdigest()=='c031189a858af796ea1e3475fa9256fb1aa9bf91eb0b516afce4aad6b6b4fec2','BUNDLE_REFUSED')
    env={'LANG':'C','HOME':'/nonexistent','PATH':'/nonexistent','GIT_CONFIG_NOSYSTEM':'1',
         'GIT_CONFIG_GLOBAL':'/dev/null','GIT_TERMINAL_PROMPT':'0','GIT_NO_REPLACE_OBJECTS':'1',
         'GIT_ALLOW_PROTOCOL':'file','GIT_SSL_CAINFO':'/etc/ssl/certs/ca-certificates.crt'}
    repository=ROOT/'candidate.git'
    if not repository.exists():
        repository.mkdir(mode=0o700)
        run(['-c','init.templateDir=','init','--bare','--quiet',str(repository)],env)
    info=repository.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid==0 and stat.S_IMODE(info.st_mode)==0o700,'REPOSITORY_REFUSED')
    prefix=['-c','core.hooksPath=/dev/null','--git-dir='+str(repository)]
    run([*prefix,'bundle','verify',str(bundle)],env)
    run([*prefix,'fetch','--no-tags','--no-write-fetch-head',str(bundle),
         'refs/heads/'+BRANCH+':refs/heads/'+BRANCH],env)
    run([*prefix,'merge-base','--is-ancestor',BASE,HEAD],env)
    require(subprocess.check_output([GIT,*prefix,'rev-parse','refs/heads/'+BRANCH],env=env).strip().decode()==HEAD,'HEAD_REFUSED')
    fd=os.open('/var/lib/mrjam-github-app/app-credentials.json',os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as stream:
        info=os.fstat(stream.fileno())
        require(info.st_uid==0 and stat.S_IMODE(info.st_mode)==0o400 and info.st_size<=32768,'CREDENTIAL_REFUSED')
        credentials=P.A.checked(json.loads(stream.read(32769)))
    require(credentials['app_id']==P.APP_ID,'APP_REFUSED')
    permissions={'contents':'write','metadata':'read'}
    status,created=P.api('/app/installations/'+str(P.INSTALLATION)+'/access_tokens',P.A.jwt(credentials),'POST',
                        {'repository_ids':[1437120781],'permissions':permissions})
    require(status==201 and type(created.get('token')) is str,'TOKEN_REFUSED')
    token=created['token']
    try:
        require(created['permissions']==permissions,'PERMISSIONS_REFUSED')
        status,repo=P.api('/repos/MrJ-am/mrjam-plateforme',token)
        require(status==200 and repo['id']==1437120781 and repo['private'] is True,'PRIVATE_REPOSITORY_REQUIRED')
        status,main=P.api('/repos/MrJ-am/mrjam-plateforme/git/ref/heads/main',token)
        require(status==200 and main['object']['sha']==BASE,'MAIN_MOVED')
        path='/repos/MrJ-am/mrjam-plateforme/git/ref/heads/'+BRANCH
        exists=False
        try:
            status,ref=P.api(path,token)
            require(status==200 and ref['object']['sha']==HEAD,'CANDIDATE_BRANCH_EXISTS')
            exists=True
        except HTTPError as error:
            require(error.code==404,'BRANCH_OBSERVATION_FAILED')
        if not exists:
            settings={'credential.helper':'','http.proxy':'','http.followRedirects':'false',
                      'http.sslVerify':'true','http.extraHeader':'',
                      'http.https://github.com/.extraHeader':'Authorization: Basic '+base64.b64encode(('x-access-token:'+token).encode()).decode(),
                      'protocol.allow':'never','protocol.https.allow':'always'}
            env.update(GIT_ALLOW_PROTOCOL='https',GIT_CONFIG_COUNT=str(len(settings)))
            for i,(key,value) in enumerate(settings.items()):
                env['GIT_CONFIG_KEY_'+str(i)]=key;env['GIT_CONFIG_VALUE_'+str(i)]=value
            run([*prefix,'push','--quiet','--no-verify','--force-with-lease=refs/heads/'+BRANCH+':',
                 'https://github.com/MrJ-am/mrjam-plateforme.git',HEAD+':refs/heads/'+BRANCH],env)
        status,ref=P.api(path,token)
        require(status==200 and ref['object']['sha']==HEAD,'PUBLISHED_HEAD_REFUSED')
        status,main=P.api('/repos/MrJ-am/mrjam-plateforme/git/ref/heads/main',token)
        require(status==200 and main['object']['sha']==BASE,'MAIN_CHANGED')
    finally:
        status,_=P.api('/installation/token',token,'DELETE')
        require(status==204,'TOKEN_REVOCATION_FAILED')
    print(json.dumps({'code':'PRIVATE_CANDIDATE_BRANCH_PUBLISHED','repository':'MrJ-am/mrjam-plateforme',
                      'branch':BRANCH,'head':HEAD,'main_unchanged':True,'token_revoked':True,
                      'workflow_files_at_head':0,'deployment_performed':False}))

if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps({'code':str(error) if isinstance(error,RuntimeError) else 'PUBLICATION_FAILED',
                          'exception_type':type(error).__name__}))
        raise SystemExit(1) from None
