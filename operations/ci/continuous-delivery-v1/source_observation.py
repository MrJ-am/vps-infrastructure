"""Fresh protected observation of an open proposal and its exact commit tree."""
import github_proposals as P
import source_snapshot as S

def observe(proposal,credentials,request=P.api):
    P.A.checked(credentials)
    S.require(credentials['app_id']==P.APP_ID,'APP_REFUSED')
    S.require(type(proposal) is dict and set(proposal)=={'repository','repository_id','number','draft','head','base','branch'}
        and proposal.get('repository') in P.REPOSITORIES
        and proposal['repository_id']==P.REPOSITORIES[proposal['repository']] and proposal['draft'] is False
        and type(proposal.get('number')) is int and 0<proposal['number']<2**31
        and type(proposal.get('head')) is str and S.OID.fullmatch(proposal['head']), 'PROPOSAL_SCOPE_REFUSED')
    repository=proposal['repository'];base='/repos/MrJ-am/'+repository
    status,created=request('/app/installations/'+str(P.INSTALLATION)+'/access_tokens',P.A.jwt(credentials),'POST',{
        'repository_ids':[P.REPOSITORIES[repository]],'permissions':P.READ_PERMISSIONS})
    S.require(status==201 and type(created) is dict and type(created.get('token')) is str,'READ_TOKEN_REFUSED')
    token=created['token']
    try:
        S.require(created.get('permissions')==P.READ_PERMISSIONS,'TOKEN_PERMISSIONS_REFUSED')
        def check():
            status,current=request(base+'/pulls/'+str(proposal['number']),token)
            S.require(status==200 and P.project(repository,current)==proposal,'PROPOSAL_OBSERVATION_CHANGED')
        check()
        status,commit=request(base+'/git/commits/'+proposal['head'],token)
        S.require(status==200 and type(commit) is dict and commit.get('sha')==proposal['head']
            and type(commit.get('tree')) is dict and type(commit['tree'].get('sha')) is str
            and S.OID.fullmatch(commit['tree']['sha']),'COMMIT_TREE_REFUSED')
        check()
        return {'repository':'MrJ-am/'+repository,'revision':proposal['head'],'tree_sha':commit['tree']['sha']}
    finally:
        status,_=request('/installation/token',token,'DELETE');S.require(status==204,'TOKEN_REVOCATION_FAILED')
