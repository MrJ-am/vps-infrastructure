# Appended to the pinned receiver definitions by the administrative SSH relay.
# No source content or token leaves this process. The temporary token is revoked.
EXPECTED_REPOS={'vps-infrastructure','mrjam-plateforme','mrjam-validation','Signature',
                'matheval','vision','apprendre-a-demontrer','style-mrjam','etp-vie-affective'}
INSTALLATION=178130872
def api(path,authorization,method='GET',body=None):
    require(path.startswith('/') and not path.startswith('//'),'API_PATH_REFUSED')
    request=urllib.request.Request('https://api.github.com'+path,method=method,
        data=None if body is None else canonical(body),headers={
            'Authorization':'Bearer '+authorization,'Accept':'application/vnd.github+json',
            'Content-Type':'application/json','X-GitHub-Api-Version':'2022-11-28','User-Agent':'mrjam-installation-audit'})
    tls=ssl.create_default_context(cafile='/etc/ssl/certs/ca-certificates.crt')
    with urllib.request.build_opener(NoRedirect,urllib.request.HTTPSHandler(context=tls)).open(request,timeout=20) as response:
        raw=response.read(1048577);require(len(raw)<=1048576,'API_RESPONSE_LIMIT')
        return response.status,json.loads(raw) if raw else None
def audit():
    require(os.getuid()==0,'ADMIN_REQUIRED')
    fd=os.open(DIRECTORY/'app-credentials.json',os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        info=os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid==0 and stat.S_IMODE(info.st_mode)==0o400 and info.st_nlink==1 and info.st_size<=32768,'CREDENTIAL_METADATA_REFUSED')
        value=checked(json.loads(os.read(fd,32769)))
    finally:os.close(fd)
    require(value['app_id']==5592797,'APP_REFUSED')
    authorization=jwt(value)
    status,installation=api('/app/installations/'+str(INSTALLATION),authorization)
    require(status==200 and installation.get('app_id')==value['app_id']
        and installation.get('account',{}).get('id')==12571490
        and installation.get('repository_selection')=='selected'
        and installation.get('permissions')==PERMISSIONS
        and installation.get('suspended_at') is None,'INSTALLATION_SCOPE_REFUSED')
    status,created=api('/app/installations/'+str(INSTALLATION)+'/access_tokens',authorization,'POST',{
        'permissions':{'contents':'read','metadata':'read','pull_requests':'read'}})
    require(status==201 and type(created.get('token')) is str,'TOKEN_REFUSED')
    token=created['token']
    try:
        require(created.get('permissions')=={'contents':'read','metadata':'read','pull_requests':'read'},'TOKEN_SCOPE_REFUSED')
        status,inventory=api('/installation/repositories?per_page=100',token)
        repos=inventory.get('repositories',[])
        require(status==200 and inventory.get('total_count')==9 and len(repos)==9,'REPOSITORY_COUNT_REFUSED')
        require({r.get('full_name') for r in repos}=={'MrJ-am/'+n for n in EXPECTED_REPOS},'REPOSITORY_SET_REFUSED')
        observed=[]
        for repo in sorted(repos,key=lambda r:r['full_name']):
            require(repo.get('owner',{}).get('id')==12571490 and type(repo.get('id')) is int,'REPOSITORY_OWNER_REFUSED')
            status,head=api('/repos/'+repo['full_name']+'/git/ref/heads/main',token)
            revision=head.get('object',{}).get('sha','')
            require(status==200 and re.fullmatch('[0-9a-f]{40}',revision),'HEAD_REFUSED')
            observed.append({'id':repo['id'],'full_name':repo['full_name'],'private':repo['private'],'main':revision})
    finally:
        status,_=api('/installation/token',token,'DELETE');require(status==204,'TOKEN_REVOCATION_FAILED')
    result={'schema_version':1,'app_id':value['app_id'],'installation_id':INSTALLATION,
            'repository_selection':'selected','permissions':PERMISSIONS,'repositories':observed,
            'read_token_revoked':True,'complete_installation_repository_scope_verified':True,'pipeline_activated':False}
    fd=os.open(DIRECTORY/'installation-scope.json',os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o400)
    with os.fdopen(fd,'wb') as stream:stream.write(canonical(result));stream.flush();os.fsync(stream.fileno())
    print(json.dumps(result,sort_keys=True))
try:audit()
except Exception:
    print('{"code":"INSTALLATION_AUDIT_REFUSED_VERIFY_STATE_BEFORE_RETRY"}');raise SystemExit(1) from None
