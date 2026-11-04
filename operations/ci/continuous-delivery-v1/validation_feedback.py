"""Publish a signed validation result to its exact GitHub proposal commit.

A status is feedback, never a deployment capability. The protected caller
resolves the admission policy and verifies the captured artifact bytes first.
"""
import re
import github_proposals as P
import intake_queue as Q
from source_snapshot import require

PERMISSIONS={'metadata':'read','pull_requests':'read','statuses':'write'}
CONTEXT='mrjam/independent-validation'

def publish(proposal,run,policy,envelope,credentials,*,verify,request=P.api):
    Q.checked(proposal)
    require(proposal['draft'] is False,'FEEDBACK_DRAFT_REFUSED')
    require(verify(envelope,policy),'FEEDBACK_SIGNATURE_REFUSED')
    digest=envelope['payload']['proposal_sha256']
    require(type(digest) is str and re.fullmatch('[0-9a-f]{64}',digest)
        and policy['accepted_proposals']==[digest],'FEEDBACK_ADMISSION_REFUSED')
    require(type(run) is dict and type(run.get('id')) is int and run['id']>0
        and run.get('terminal') is True and run.get('status')=='success'
        and run.get('proposal_sha256')==digest and run.get('rules_revision')==policy['rules_revision'],
        'FEEDBACK_RUN_REFUSED')
    require(any(s['repository']=='MrJ-am/'+proposal['repository'] and s['revision']==proposal['head']
        for s in policy['sources']),'FEEDBACK_SOURCE_REFUSED')
    P.A.checked(credentials);require(credentials['app_id']==P.APP_ID,'FEEDBACK_APP_REFUSED')
    body={'state':'success','context':CONTEXT,
        'description':str(len(policy['required_steps']))+' contrôles réussis ; signature Ed25519 vérifiée',
        'target_url':'https://forge.mrj.am/MrJ-am/mrjam-validation/actions/runs/'+str(run['id'])}
    base='/repos/MrJ-am/'+proposal['repository']
    status,created=request('/app/installations/'+str(P.INSTALLATION)+'/access_tokens',P.A.jwt(credentials),'POST',
        {'repository_ids':[proposal['repository_id']],'permissions':PERMISSIONS})
    require(status==201 and type(created) is dict and type(created.get('token')) is str,'FEEDBACK_TOKEN_REFUSED')
    token=created['token']
    try:
        require(created.get('permissions')==PERMISSIONS,'FEEDBACK_PERMISSIONS_REFUSED')
        status,current=request(base+'/pulls/'+str(proposal['number']),token)
        require(status==200 and P.project(proposal['repository'],current)==proposal,'FEEDBACK_PROPOSAL_CHANGED')
        status,rows=request(base+'/commits/'+proposal['head']+'/statuses?per_page=100&page=1',token)
        require(status==200 and type(rows) is list and len(rows)<=100,'FEEDBACK_STATUS_LIST_REFUSED')
        # Reconcile a lost POST response without appending the same status.
        # Another principal's status never satisfies our publication receipt.
        ours=[r for r in rows if type(r) is dict and r.get('context')==CONTEXT
            and r.get('creator',{}).get('login')==credentials['slug']+'[bot]'
            and r.get('creator',{}).get('type')=='Bot']
        existing=ours[0] if ours else None
        recovered=existing is not None and all(existing.get(k)==v for k,v in body.items())
        if recovered:result=existing
        else:
            status,result=request(base+'/statuses/'+proposal['head'],token,'POST',body)
            require(status==201 and type(result) is dict and all(result.get(k)==v for k,v in body.items()),
                'FEEDBACK_PUBLICATION_REFUSED')
        require(type(result.get('id')) is int and result['id']>0,'FEEDBACK_STATUS_ID_REFUSED')
    finally:
        status,_=request('/installation/token',token,'DELETE');require(status==204,'FEEDBACK_REVOCATION_FAILED')
    return {'repository':proposal['repository'],'head':proposal['head'],'proposal_sha256':digest,
        'run_id':run['id'],'status_id':result['id'],'recovered_existing':recovered,
        'token_revoked':True,'deployment_authorized':False}
