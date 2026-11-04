"""Publish one fixed, comment-only qualification PR using a scoped App token."""
import base64,hashlib,json,os,re,stat,sys
from urllib.error import HTTPError
sys.path.insert(0,'/nix/store/qmzbv6zskr9qzhh3ifqs010jz26q2jlh-mrjam-protected-admission-controller-1/lib')
import github_proposals as P

BASE='bf4d301b837c350ec61f806d06571165c16a8df5'
REPO='/repos/MrJ-am/mrjam-plateforme'
BRANCH='spectre/readiness-authority-qualification-20261104'
FILE='crates/server/src/runtime.rs'
BEFORE='c4ae94cd1659da35eef5a572fe7dd47cbb13d4c877e74b6a8a93da458c3f847f'
AFTER='14c7c7431bb6cce69e206b3700b39a6aadf71f1518d9b071d03ea469cad65652'

def require(ok,code):
    if not ok:raise RuntimeError(code)

def main():
    require(os.getuid()==0 and os.uname().nodename=='srv1982677' and len(sys.argv)==1,'PUBLICATION_HOST_REFUSED')
    fd=os.open('/var/lib/mrjam-github-app/app-credentials.json',os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as stream:
        info=os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_uid==0 and stat.S_IMODE(info.st_mode)==0o400
            and info.st_size<=32768,'PUBLICATION_CREDENTIAL_REFUSED')
        credentials=P.A.checked(json.loads(stream.read(32769)))
    require(credentials['app_id']==P.APP_ID,'PUBLICATION_APP_REFUSED')
    permissions={'contents':'write','pull_requests':'write','metadata':'read'}
    status,created=P.api('/app/installations/'+str(P.INSTALLATION)+'/access_tokens',P.A.jwt(credentials),'POST',
        {'repository_ids':[1437120781],'permissions':permissions})
    require(status==201 and type(created.get('token')) is str,'PUBLICATION_TOKEN_REFUSED')
    token=created['token']
    try:
        require(created.get('permissions')==permissions,'PUBLICATION_SCOPE_REFUSED')
        def api(path,method='GET',body=None,expected=200):
            status,value=P.api(REPO+path,token,method,body)
            require(status==expected,'PUBLICATION_API_STATUS_REFUSED');return value
        repo=api('');require(repo['id']==1437120781 and repo['private'] is True and repo['default_branch']=='main',
            'PUBLICATION_REPOSITORY_REFUSED')
        require(api('/git/ref/heads/main')['object']['sha']==BASE,'PUBLICATION_MAIN_MOVED')
        base=api('/git/commits/'+BASE);tree=api('/git/trees/'+base['tree']['sha']+'?recursive=1')
        require(tree.get('truncated') is False and not any(row['path'].startswith('.github/workflows/')
            and row['path'].endswith(('.yml','.yaml')) for row in tree['tree']),'PUBLICATION_WORKFLOW_REFUSED')
        source=api('/contents/'+FILE+'?ref='+BASE)
        require(source['type']=='file' and source['encoding']=='base64','PUBLICATION_SOURCE_REFUSED')
        old=base64.b64decode(source['content']);require(hashlib.sha256(old).hexdigest()==BEFORE,'PUBLICATION_SOURCE_CHANGED')
        needle=b'async fn ready(State(state): State<RuntimeState>) -> Response {'
        comment=b'/// A readiness response alone does not authorize deployment.\n'
        require(old.count(needle)==1,'PUBLICATION_INSERTION_REFUSED');new=old.replace(needle,comment+needle)
        require(hashlib.sha256(new).hexdigest()==AFTER,'PUBLICATION_PATCH_REFUSED')
        updated=api('/git/trees','POST',{'base_tree':base['tree']['sha'],
            'tree':[{'path':FILE,'mode':'100644','type':'blob','content':new.decode()}]},201)
        head=None
        try:head=api('/git/ref/heads/'+BRANCH)['object']['sha']
        except HTTPError as error:require(error.code==404,'PUBLICATION_BRANCH_READ_REFUSED')
        if head is None:
            commit=api('/git/commits','POST',{'message':'docs(server): distinguish readiness from deployment authority',
                'tree':updated['sha'],'parents':[BASE]},201)
            head=commit['sha']
            require(api('/git/ref/heads/main')['object']['sha']==BASE,'PUBLICATION_MAIN_MOVED')
            api('/git/refs','POST',{'ref':'refs/heads/'+BRANCH,'sha':head},201)
        commit=api('/git/commits/'+head)
        require(commit['tree']['sha']==updated['sha'] and [p['sha'] for p in commit['parents']]==[BASE],
            'PUBLICATION_EXISTING_BRANCH_REFUSED')
        diff=api('/compare/'+BASE+'...'+head)
        require(diff.get('status')=='ahead' and diff.get('ahead_by')==1 and diff.get('behind_by')==0
            and len(diff.get('files',[]))==1 and diff['files'][0]['filename']==FILE
            and diff['files'][0]['additions']==1 and diff['files'][0]['deletions']==0,'PUBLICATION_DIFF_REFUSED')
        pulls=api('/pulls?state=all&head=MrJ-am:'+BRANCH+'&base=main&per_page=100')
        require(len(pulls)<=1,'PUBLICATION_PULL_AMBIGUOUS')
        if not pulls:
            require(api('/git/ref/heads/main')['object']['sha']==BASE,'PUBLICATION_MAIN_MOVED')
            pull=api('/pulls','POST',{'title':'Préciser la séparation entre disponibilité et autorisation de livraison',
                'head':BRANCH,'base':'main','draft':False,
                'body':'Le commentaire de `/readyz` précise qu’une réponse de disponibilité ne constitue pas, à elle seule, une autorisation de déploiement.\n\nCette modification documentaire sert aussi à qualifier une nouvelle livraison par la chaîne automatique protégée. La validation indépendante, la revue technique et le déploiement restent à observer ; aucun succès de bout en bout n’est présumé.'},201)
        else:pull=pulls[0]
        require(pull['head']['sha']==head and pull['base']['sha']==BASE and pull['head']['repo']['id']==1437120781,
            'PUBLICATION_PULL_BINDING_REFUSED')
        result={'code':'READINESS_AUTHORITY_QUALIFICATION_PR_PUBLISHED','repository':'MrJ-am/mrjam-plateforme',
            'number':pull['number'],'url':pull['html_url'],'head':head,'base':BASE,'branch':BRANCH,
            'file':FILE,'file_sha256':AFTER,'main_written':False,'token_revoked':True}
    finally:
        status,_=P.api('/installation/token',token,'DELETE');require(status==204,'PUBLICATION_TOKEN_REVOCATION_FAILED')
    print(json.dumps(result,sort_keys=True))

if __name__=='__main__':
    try:main()
    except Exception as error:
        code=str(error) if type(error) is RuntimeError and re.fullmatch('[A-Z_]{1,80}',str(error)) else 'PUBLICATION_FAILED'
        print(json.dumps({'code':code,'exception_type':type(error).__name__,'http_status':getattr(error,'code',None)}))
        raise SystemExit(2) from None
