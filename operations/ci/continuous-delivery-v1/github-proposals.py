"""Read-only discovery of Cloud PRs. A snapshot grants no validation or release."""
import json,os,re,ssl,stat,time,urllib.request
from pathlib import Path
import github_app_auth as A

REPOSITORIES={'Signature':1374156543,'apprendre-a-demontrer':1371197112,
 'etp-vie-affective':1433178398,'matheval':1437121919,'mrjam-plateforme':1437120781,
 'mrjam-validation':1437121466,'style-mrjam':1379878757,'vision':1354721741,
 'vps-infrastructure':1375074191}
INSTALLATION=178130872
APP_ID=5592797
READ_PERMISSIONS={'contents':'read','metadata':'read','pull_requests':'read'}
SHA=re.compile('[0-9a-f]{40}\\Z')

def project(repository,value):
    A.require(repository in REPOSITORIES and type(value) is dict,'PULL_REFUSED')
    number=value.get('number');A.require(type(number) is int and 0<number<2**31,'PULL_NUMBER_REFUSED')
    A.require(value.get('state')=='open' and type(value.get('draft')) is bool,'PULL_STATE_REFUSED')
    base=value.get('base',{});head=value.get('head',{})
    expected=REPOSITORIES[repository]
    A.require(base.get('repo',{}).get('id')==expected and base.get('ref')=='main','PULL_BASE_REFUSED')
    # Fork proposals need a separate, explicitly designed source transport.
    A.require(type(head.get('repo')) is dict and head['repo'].get('id')==expected,'PULL_REPOSITORY_REFUSED')
    for ref in (base,head):
        A.require(ref.get('repo',{}).get('full_name')=='MrJ-am/'+repository,'PULL_OWNER_REFUSED')
        A.require(type(ref.get('sha')) is str and SHA.fullmatch(ref['sha']),'PULL_SHA_REFUSED')
    branch=head.get('ref')
    A.require(type(branch) is str and 0<len(branch.encode())<=255 and not any(ord(c)<33 or c in '~^:?*[\\' for c in branch)
        and '..' not in branch and '@{' not in branch and not branch.startswith('/') and not branch.endswith(('/','.'))
        and all(p and not p.startswith('.') and not p.endswith('.lock') for p in branch.split('/')),'PULL_BRANCH_REFUSED')
    return {'repository':repository,'repository_id':expected,'number':number,'draft':value['draft'],
            'head':head['sha'],'base':base['sha'],'branch':branch}

def api(path,token,method='GET',body=None):
    A.require(path.startswith('/') and not path.startswith('//'),'API_PATH_REFUSED')
    request=urllib.request.Request('https://api.github.com'+path,method=method,
        data=None if body is None else A.canonical(body),headers={
            'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json',
            'Content-Type':'application/json','X-GitHub-Api-Version':'2022-11-28','User-Agent':'mrjam-proposal-discovery'})
    tls=ssl.create_default_context(cafile='/etc/ssl/certs/ca-certificates.crt')
    with urllib.request.build_opener(urllib.request.ProxyHandler({}),A.NoRedirect,urllib.request.HTTPSHandler(context=tls)).open(request,timeout=20) as response:
        raw=response.read(2097153);A.require(len(raw)<=2097152,'API_RESPONSE_LIMIT')
        return response.status,json.loads(raw) if raw else None

def discover(credentials,request=api):
    A.checked(credentials);A.require(credentials['app_id']==APP_ID,'APP_REFUSED')
    status,created=request('/app/installations/'+str(INSTALLATION)+'/access_tokens',A.jwt(credentials),'POST',{
        'repository_ids':sorted(REPOSITORIES.values()),'permissions':READ_PERMISSIONS})
    A.require(status==201 and type(created.get('token')) is str,'READ_TOKEN_REFUSED')
    token=created['token'];proposals=[];ignored=[]
    try:
        A.require(created.get('permissions')==READ_PERMISSIONS,'TOKEN_PERMISSIONS_REFUSED')
        for repository in sorted(REPOSITORIES):
            seen=set()
            for page in range(1,21):
                status,rows=request('/repos/MrJ-am/'+repository+'/pulls?state=open&base=main&sort=created&direction=asc&per_page=100&page='+str(page),token)
                A.require(status==200 and type(rows) is list and len(rows)<=100,'PULL_PAGE_REFUSED')
                for row in rows:
                    number=row.get('number') if type(row) is dict else None
                    A.require(type(number) is int and number not in seen,'PULL_PAGE_CHANGED');seen.add(number)
                    try:proposals.append(project(repository,row))
                    except A.Refused as error:
                        # One malformed/fork proposal must not block other repositories.
                        ignored.append({'repository':repository,'number':number,'code':str(error)})
                if len(rows)<100:break
            else:raise A.Refused('PULL_PAGINATION_LIMIT')
    finally:
        status,_=request('/installation/token',token,'DELETE');A.require(status==204,'TOKEN_REVOCATION_FAILED')
    return {'schema_version':1,'scope':'discovery-only-no-admission','observed_at':int(time.time()),
            'app_id':APP_ID,'installation_id':INSTALLATION,'proposals':proposals,'ignored':ignored,
            'read_token_revoked':True,'deployment_authorized':False}

def credential_metadata(info,uid,gid):
    # systemd LoadCredential exposes root:root 0440 files through a private
    # per-unit credential mount/ACL, including for DynamicUser services.
    A.require(stat.S_ISREG(info.st_mode) and 0<info.st_size<=32768
        and stat.S_IMODE(info.st_mode) in {0o400,0o440}
        and info.st_uid in {0,uid} and info.st_gid in {0,gid},'CREDENTIAL_FILE_REFUSED')

def main():
    path=Path(os.environ['CREDENTIALS_DIRECTORY'])/'github-app'
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        credential_metadata(os.fstat(fd),os.getuid(),os.getgid())
        credentials=A.checked(json.loads(os.read(fd,32769)))
    finally:os.close(fd)
    result=discover(credentials)
    state=Path(os.environ['STATE_DIRECTORY'])
    temporary=state/'proposals.next'
    fd=os.open(temporary,os.O_CREAT|os.O_TRUNC|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:stream.write(A.canonical(result));stream.flush();os.fsync(stream.fileno())
    os.replace(temporary,state/'proposals.json')
    fd=os.open(state,os.O_DIRECTORY|os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)
    print(json.dumps({'code':'PROPOSALS_OBSERVED','proposals':len(result['proposals']),'ignored':len(result['ignored'])}))

if __name__=='__main__':
    try:main()
    except Exception:
        print('{"code":"PROPOSAL_DISCOVERY_FAILED"}');raise SystemExit(1) from None
