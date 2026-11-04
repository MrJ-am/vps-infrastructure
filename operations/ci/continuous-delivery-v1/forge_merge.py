"""Fast-forward only, with a separate merger and freshly verified authority."""
import http.client,json
import forge_review as V
import delivery_roles as R
from source_snapshot import require

class API(V.API):
    def __call__(self,method,suffix,body=None):
        if method=='GET':return super().__call__(method,suffix,body)
        require(method=='POST' and suffix==self.pull+'/merge' and body=={
            'Do':'fast-forward-only','head_commit_id':self.head,'force_merge':False,
            'merge_when_checks_succeed':False,'delete_branch_after_merge':False},'MERGE_API_ROUTE_REFUSED')
        c=http.client.HTTPConnection('127.0.0.1',3004,timeout=30)
        try:
            c.request('POST','/api/v1/repos/MrJ-am/'+self.repository+suffix,json.dumps(body),
                headers={'Host':'forge.mrj.am','Authorization':'token '+self.token,'Content-Type':'application/json'})
            response=c.getresponse();raw=response.read(1048577)
            require(len(raw)<=1048576 and response.status in (200,201,204),'PROTECTED_MERGE_REFUSED')
            return json.loads(raw) if raw else None
        finally:c.close()

def merge(proposal,number,run,policy,envelope,receipt,request,*,verify):
    branch=V.M.branch_name(proposal)
    require(verify(envelope,policy),'MERGE_SIGNATURE_REFUSED')
    digest=envelope['payload']['proposal_sha256']
    require(policy['accepted_proposals']==[digest] and run.get('proposal_sha256')==digest
        and run.get('rules_revision')==policy['rules_revision'] and run.get('terminal') is True
        and run.get('status')=='success','MERGE_RUN_REFUSED')
    require(any(s['repository']=='MrJ-am/'+proposal['repository'] and s['revision']==proposal['head']
        for s in policy['sources']),'MERGE_SOURCE_REFUSED')
    require(receipt.get('repository')==proposal['repository'] and receipt.get('number')==number
        and receipt.get('head')==proposal['head'] and receipt.get('proposal_sha256')==digest
        and receipt.get('reviewer')==R.ROLES['review'] and receipt.get('human_review') is False,
        'MERGE_REVIEW_RECEIPT_REFUSED')
    repo=request('GET','')
    require(repo.get('id')==V.M.FORGE_IDS[proposal['repository']] and repo.get('full_name')=='MrJ-am/'+proposal['repository']
        and repo.get('private') is True and repo.get('has_actions') is False and repo.get('default_branch')=='main',
        'MERGE_REPOSITORY_REFUSED')
    protection=request('GET','/branch_protections/main')
    R.verify_protection(protection,protection,R.protection_change(proposal['repository'],protection))
    path='/pulls/'+str(number);pr=request('GET',path)
    require(pr.get('head',{}).get('ref')==branch and pr['head'].get('sha')==proposal['head']
        and pr.get('base',{}).get('ref')=='main' and pr.get('user',{}).get('login')==R.ROLES['mirror'],
        'MERGE_PROPOSAL_CHANGED')
    rows=[]
    for page in range(1,100):
        part=request('GET',path+'/reviews?limit=50&page='+str(page))
        require(type(part) is list and len(part)<=50,'MERGE_REVIEW_PAGE_REFUSED');rows+=part
        if len(part)<50:break
    else:require(False,'MERGE_REVIEW_LIMIT')
    require(any(r.get('id')==receipt.get('review_id') and r.get('user',{}).get('login')==R.ROLES['review']
        and r.get('commit_id')==proposal['head'] and r.get('state')=='APPROVED' and r.get('official') is True
        and r.get('stale') is False and r.get('dismissed') is False for r in rows),'MERGE_REVIEW_REFUSED')
    require(not any(r.get('state')=='REQUEST_CHANGES' and r.get('official') is True
        and r.get('dismissed') is False for r in rows),'MERGE_CHANGES_REQUESTED')
    recovered=pr.get('merged') is True
    if not recovered:
        require(pr.get('state')=='open' and pr.get('mergeable') is True,'MERGE_NOT_READY')
        require(request('GET','/branches/main')['commit']['id']==proposal['base'],'MERGE_BASE_MOVED')
        request('POST',path+'/merge',{'Do':'fast-forward-only','head_commit_id':proposal['head'],
            'force_merge':False,'merge_when_checks_succeed':False,'delete_branch_after_merge':False})
    pr=request('GET',path)
    require(pr.get('merged') is True and pr.get('merged_by',{}).get('login')==R.ROLES['merge']
        and pr.get('merge_commit_sha')==proposal['head']
        and request('GET','/branches/main')['commit']['id']==proposal['head'],'MERGE_CONFIRMATION_REFUSED')
    require(request('GET','/branch_protections/main')==protection,'MERGE_PROTECTION_CHANGED')
    return {'repository':proposal['repository'],'number':number,'head':proposal['head'],
        'proposal_sha256':digest,'review_id':receipt['review_id'],'merger':R.ROLES['merge'],
        'protected_fast_forward':True,'recovered_existing':recovered,'deployed':False}
