"""Independent technical approval bound to signed validation, never a merge.

The protected caller verifies captured bytes and freshly observes GitHub and
the CI run. This component rechecks the signature and all source/run bindings.
No human review is created or impersonated.
"""
import http.client,json
import forge_proposal as M
import delivery_roles as R
from source_snapshot import require

class API(M.API):
    def __init__(self,proposal,number,token,policy_token):
        super().__init__(proposal['repository'],M.branch_name(proposal),token,policy_token)
        require(type(number) is int and number>0,'REVIEW_NUMBER_REFUSED')
        self.pull='/pulls/'+str(number);self.head=proposal['head']
    def __call__(self,method,suffix,body=None):
        if method=='GET' and suffix in ('','/branches/main','/branch_protections/main'):
            return super().__call__(method,suffix,body)
        allowed=method=='GET' and body is None and (suffix==self.pull or
            suffix.startswith(self.pull+'/reviews?limit=50&page=') and
            suffix.removeprefix(self.pull+'/reviews?limit=50&page=').isdigit() and
            1<=int(suffix.removeprefix(self.pull+'/reviews?limit=50&page='))<=99)
        allowed=allowed or (method=='POST' and suffix==self.pull+'/reviews' and type(body) is dict
            and set(body)=={'event','commit_id','body'} and body['event']=='APPROVED' and body['commit_id']==self.head)
        allowed=allowed or (method=='POST' and suffix=='/statuses/'+self.head and type(body) is dict
            and set(body)=={'state','context','description','target_url'} and body['state']=='success'
            and body['context']==R.CONTEXT)
        require(allowed,'REVIEW_API_ROUTE_REFUSED')
        c=http.client.HTTPConnection('127.0.0.1',3004,timeout=20)
        try:
            c.request(method,'/api/v1/repos/MrJ-am/'+self.repository+suffix,
                body=None if body is None else json.dumps(body),headers={'Host':'forge.mrj.am',
                    'Authorization':'token '+self.token,'Content-Type':'application/json'})
            response=c.getresponse();raw=response.read(1048577)
            require(len(raw)<=1048576 and response.status in (200,201),'REVIEW_API_REFUSED')
            return json.loads(raw)
        finally:c.close()

def approve(proposal,number,run,policy,envelope,request,*,verify):
    branch=M.branch_name(proposal)
    require(verify(envelope,policy),'REVIEW_SIGNATURE_REFUSED')
    digest=envelope['payload']['proposal_sha256']
    require(policy['accepted_proposals']==[digest] and run.get('proposal_sha256')==digest
        and run.get('rules_revision')==policy['rules_revision'] and run.get('terminal') is True
        and run.get('status')=='success' and type(run.get('id')) is int and run['id']>0,'REVIEW_RUN_REFUSED')
    require(any(s['repository']=='MrJ-am/'+proposal['repository'] and s['revision']==proposal['head']
        for s in policy['sources']),'REVIEW_SOURCE_REFUSED')
    repo=request('GET','')
    require(repo.get('id')==M.FORGE_IDS[proposal['repository']] and repo.get('full_name')=='MrJ-am/'+proposal['repository']
        and repo.get('private') is True and repo.get('has_actions') is False and repo.get('default_branch')=='main',
        'REVIEW_REPOSITORY_REFUSED')
    protection=request('GET','/branch_protections/main')
    R.verify_protection(protection,protection,R.protection_change(proposal['repository'],protection))
    path='/pulls/'+str(number)
    def current():
        pr=request('GET',path)
        require(pr.get('number')==number and pr.get('state')=='open' and pr.get('merged') is False
            and pr.get('head',{}).get('ref')==branch and pr['head'].get('sha')==proposal['head']
            and pr.get('base',{}).get('ref')=='main' and pr.get('user',{}).get('login')==R.ROLES['mirror'],
            'REVIEW_PROPOSAL_CHANGED')
        require(request('GET','/branches/main')['commit']['id']==proposal['base'],'REVIEW_BASE_MOVED')
    def reviews():
        result=[]
        for page in range(1,100):
            rows=request('GET',path+'/reviews?limit=50&page='+str(page))
            require(type(rows) is list and len(rows)<=50,'REVIEW_PAGE_REFUSED');result+=rows
            if len(rows)<50:return result
        require(False,'REVIEW_PAGINATION_LIMIT')
    def accepted(row):
        return row.get('user',{}).get('login')==R.ROLES['review'] and row.get('state')=='APPROVED' and \
            row.get('commit_id')==proposal['head'] and row.get('official') is True and \
            row.get('stale') is False and row.get('dismissed') is False and row.get('body')==body
    body='Revue technique automatique indépendante.\nCommit : '+proposal['head']+'\nAttestation : '+digest+\
        '\nSignature Ed25519 et artefacts vérifiés ; '+str(len(policy['required_steps']))+' contrôles réussis.'+\
        '\nValidation : https://forge.mrj.am/MrJ-am/mrjam-validation/actions/runs/'+str(run['id'])+\
        '\nCette revue technique ne représente aucune approbation humaine et ne déploie rien.'
    current();rows=reviews()
    require(not any(r.get('state')=='REQUEST_CHANGES' and r.get('official') is True
        and r.get('dismissed') is False for r in rows),'REVIEW_CHANGES_REQUESTED')
    matches=[r for r in rows if accepted(r)]
    if not matches:
        request('POST','/statuses/'+proposal['head'],{'state':'success','context':R.CONTEXT,
            'description':str(len(policy['required_steps']))+' contrôles ; attestation vérifiée',
            'target_url':'https://forge.mrj.am/MrJ-am/mrjam-validation/actions/runs/'+str(run['id'])})
        current()
        request('POST',path+'/reviews',{'event':'APPROVED','commit_id':proposal['head'],'body':body})
        matches=[r for r in reviews() if accepted(r)]
    require(len(matches)==1,'REVIEW_CONFIRMATION_REFUSED');current()
    require(request('GET','/branch_protections/main')==protection,'REVIEW_PROTECTION_CHANGED')
    return {'repository':proposal['repository'],'number':number,'head':proposal['head'],
        'proposal_sha256':digest,'review_id':matches[0]['id'],'reviewer':R.ROLES['review'],
        'human_review':False,'merged':False,'deployed':False}
