"""Exact workflow dispatch and recovery by its server-recorded input digest.

The caller verifies root admission before calling this module. A run status is
not a validation attestation and grants no deployment authority. All requests
use the fixed protected validation repository, never candidate-supplied URLs.
"""
import base64,hashlib,json,re
from source_snapshot import require

BASE='/api/v1/repos/MrJ-am/mrjam-validation'
WORKFLOW='independent-validation.yml'
WORKFLOW_SHA='cd01f21d4df118d1c52d9e76ab600e6bebbd746415c4f57cc744c8d5f6f2b5de'
TERMINAL={'success','failure','cancelled','skipped'}

def identify(row,proposal,rules):
    require(type(row) is dict and type(row.get('id')) is int and row['id']>0,'RUN_ID_REFUSED')
    if row.get('workflow_id')!=WORKFLOW or row.get('commit_sha')!=rules or row.get('trigger_event')!='workflow_dispatch':return None
    payload=row.get('event_payload')
    if type(payload) is str:
        require(len(payload)<=1024*1024,'RUN_PAYLOAD_LIMIT');payload=json.loads(payload)
    if type(payload) is not dict or payload.get('inputs')!={'proposal_digest':proposal}:return None
    require(type(row.get('repository')) is dict and row['repository'].get('full_name')=='MrJ-am/mrjam-validation','RUN_REPOSITORY_REFUSED')
    status=row.get('status')
    require(status in TERMINAL|{'waiting','running','blocked','unknown'},'RUN_STATUS_REFUSED')
    return {'id':row['id'],'proposal_sha256':proposal,'rules_revision':rules,'status':status,
        'terminal':status in TERMINAL,'deployment_authorized':False}

def find(request,proposal,rules,*,after_id=0):
    require(type(proposal) is str and re.fullmatch('[0-9a-f]{64}',proposal)
        and type(rules) is str and re.fullmatch('[0-9a-f]{40}',rules)
        and type(after_id) is int and after_id>=0,'DISPATCH_IDENTITY_REFUSED')
    seen=set();previous=None
    for page in range(1,101):
        response=request('GET',BASE+'/actions/runs?limit=50&page='+str(page))
        rows=response.get('workflow_runs') if type(response) is dict else None
        require(type(rows) is list and len(rows)<=50,'RUN_PAGE_REFUSED')
        for row in rows:
            require(type(row) is dict and type(row.get('id')) is int and row['id'] not in seen,'RUN_PAGE_CHANGED')
            seen.add(row['id'])
            require(previous is None or row['id']<previous,'RUN_ORDER_CHANGED');previous=row['id']
            if row['id']<=after_id:return None
            # Some Forgejo list responses omit payload: retrieve the exact run.
            if row.get('workflow_id')==WORKFLOW and row.get('commit_sha')==rules:
                detail=request('GET',BASE+'/actions/runs/'+str(row['id']))
                require(detail.get('id')==row['id'],'RUN_DETAIL_CHANGED')
                selected=identify(detail,proposal,rules)
                if selected is not None:return selected
        if len(rows)<50:return None
    require(False,'RUN_HISTORY_LIMIT')

def ensure(request,proposal,rules,*,after_id=0):
    """Recover a previously accepted dispatch before creating another run.

    If the POST outcome is lost, the controller retries reconciliation first.
    Forgejo provides no dispatch idempotency key: concurrent or still-in-flight
    requests can duplicate a validation, so the caller serializes submissions.
    No application mutation takes place here, even if a validation is repeated.
    """
    # A controller persists this lower bound before submitting a new admission.
    # An old run for the same sources must not satisfy a renewed CI request.
    existing=find(request,proposal,rules,after_id=after_id)
    if existing is not None:return {**existing,'recovered_existing':True}
    branch=request('GET',BASE+'/branches/main')
    require(type(branch) is dict and branch.get('commit',{}).get('id')==rules,'VALIDATION_RULES_MOVED')
    workflow=request('GET',BASE+'/contents/.forgejo/workflows/'+WORKFLOW+'?ref='+rules)
    require(type(workflow) is dict and workflow.get('encoding')=='base64'
        and type(workflow.get('content')) is str and len(workflow['content'])<=65536,'WORKFLOW_CONTENT_REFUSED')
    raw=base64.b64decode(workflow['content'],validate=False)
    require(hashlib.sha256(raw).hexdigest()==WORKFLOW_SHA,'WORKFLOW_CHANGED')
    response=request('POST',BASE+'/actions/workflows/'+WORKFLOW+'/dispatches',
        {'ref':'main','inputs':{'proposal_digest':proposal},'return_run_info':True})
    require(type(response) is dict and type(response.get('id')) is int and response['id']>0,'DISPATCH_RESPONSE_REFUSED')
    require(response['id']>after_id,'DISPATCH_RUN_TOO_OLD')
    detail=request('GET',BASE+'/actions/runs/'+str(response['id']))
    require(detail.get('id')==response['id'],'DISPATCH_RUN_CHANGED')
    selected=identify(detail,proposal,rules)
    require(selected is not None,'DISPATCH_INPUT_CHANGED')
    return {**selected,'recovered_existing':False}
