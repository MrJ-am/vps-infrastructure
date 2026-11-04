"""One-way fast-forward of an already accepted canonical Forgejo commit.

Caller freshly verifies signed acceptance and protected Forgejo merge. No
GitHub PR merge, force push, workflow or repository administration is allowed.
"""
import github_proposals as P
import intake_queue as Q
from source_snapshot import require

PERMISSIONS={'contents':'write','pull_requests':'read','metadata':'read'}

def sync(proposal,accepted,credentials,*,request=P.api):
    Q.checked(proposal)
    require(accepted.get('repository')==proposal['repository'] and accepted.get('head')==proposal['head']
        and accepted.get('protected_fast_forward') is True and accepted.get('merger')=='mrjam-release-merge',
        'SYNC_CANONICAL_ACCEPTANCE_REFUSED')
    P.A.checked(credentials);require(credentials['app_id']==P.APP_ID,'SYNC_APP_REFUSED')
    base='/repos/MrJ-am/'+proposal['repository']
    status,created=request('/app/installations/'+str(P.INSTALLATION)+'/access_tokens',P.A.jwt(credentials),'POST',
        {'repository_ids':[proposal['repository_id']],'permissions':PERMISSIONS})
    require(status==201 and type(created) is dict and type(created.get('token')) is str,'SYNC_TOKEN_REFUSED')
    token=created['token']
    try:
        require(created.get('permissions')==PERMISSIONS,'SYNC_PERMISSIONS_REFUSED')
        status,repo=request(base,token)
        require(status==200 and repo.get('id')==proposal['repository_id'] and repo.get('full_name')=='MrJ-am/'+proposal['repository']
            and repo.get('private') is True and repo.get('default_branch')=='main','SYNC_REPOSITORY_REFUSED')
        status,ref=request(base+'/git/ref/heads/main',token)
        require(status==200 and ref.get('ref')=='refs/heads/main' and ref.get('object',{}).get('type')=='commit',
            'SYNC_MAIN_REFUSED')
        current=ref['object']['sha'];recovered=current==proposal['head']
        if not recovered:
            require(current==proposal['base'],'SYNC_BASE_MOVED')
            status,pr=request(base+'/pulls/'+str(proposal['number']),token)
            require(status==200 and P.project(proposal['repository'],pr)==proposal,'SYNC_PROPOSAL_CHANGED')
            status,result=request(base+'/git/refs/heads/main',token,'PATCH',{'sha':proposal['head'],'force':False})
            require(status==200 and result.get('object',{}).get('sha')==proposal['head'],'SYNC_FAST_FORWARD_REFUSED')
        status,ref=request(base+'/git/ref/heads/main',token)
        require(status==200 and ref.get('object',{}).get('sha')==proposal['head'],'SYNC_CONFIRMATION_REFUSED')
    finally:
        status,_=request('/installation/token',token,'DELETE');require(status==204,'SYNC_REVOCATION_FAILED')
    return {'repository':proposal['repository'],'head':proposal['head'],'canonical_forgejo_main':True,
        'github_main_synchronized':True,'recovered_existing':recovered,'token_revoked':True,'deployed':False}
