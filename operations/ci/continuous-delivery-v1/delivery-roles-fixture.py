"""Invented Forgejo17 VM only: exercise real permissions, reviews and merges."""
import base64,importlib.util,json,sys,time
from pathlib import Path
sys.path.insert(0,'/etc/delivery-roles')
import delivery_roles as R
spec=importlib.util.spec_from_file_location('fixture','/etc/forgejo-bootstrap-fixture.py')
F=importlib.util.module_from_spec(spec);spec.loader.exec_module(F)
need=F.require
PREFIX='/api/v1/repos/MrJ-am/mrjam-plateforme'

def main():
    tokens={};checks=[]
    for role,name in R.ROLES.items():
        F.cli('admin','user','create','--username',name,'--email',name+'@synthetic.invalid',
            '--random-password','--random-password-length','64','--must-change-password=false')
        tokens[role]=F.cli('admin','user','generate-access-token','--username',name,
            '--token-name','synthetic-delivery','--scopes','write:repository','--raw').decode().strip()
    with F.core.governance_lease() as admin:
        for repository in R.APPLICATIONS:
            path='/api/v1/repos/MrJ-am/'+repository
            # Site-admin alone is not included by Forgejo's whitelist user
            # selector. Give the invented human explicit repository access.
            need(F.api(admin,'PUT',path+'/collaborators/'+R.HUMAN,{'permission':'write'})[0]==204,'SYNTHETIC_HUMAN_GRANT_FAILED')
            for name in R.ROLES.values():
                need(F.api(admin,'PUT',path+'/collaborators/'+name,{'permission':'write'})[0]==204,'ROLE_GRANT_FAILED')
            code,before=F.api(admin,'GET',path+'/branch_protections/main');need(code==200,'PROTECTION_READ_FAILED')
            change=R.protection_change(repository,before)
            need(F.api(admin,'PATCH',path+'/branch_protections/main',change)[0]==200,'RESTRICTION_PATCH_FAILED')
            code,after=F.api(admin,'GET',path+'/branch_protections/main');need(code==200,'PROTECTION_READ_FAILED')
            differences={k:{'expected':v,'actual':after.get(k)} for k,v in change.items() if after.get(k)!=v}
            if differences:print(json.dumps({'synthetic_protection_differences':differences}),flush=True)
            R.verify_protection(before,after,change)
        checks.append('real-seven-repository-restrictive-protection-roundtrip')
        for role,token in tokens.items():
            for repository in ['mrjam-validation','vps-infrastructure','synthetic-unrelated']:
                need(F.api(token,'GET','/api/v1/repos/MrJ-am/'+repository)[0] in (403,404),'ROLE_READS_OTHER_AUTHORITY')
            need(F.api(token,'PATCH',PREFIX,{'has_actions':False})[0]==403,'ROLE_IS_REPOSITORY_ADMIN')
            need(F.api(token,'PATCH',PREFIX+'/branch_protections/main',{'required_approvals':0})[0]==403,'ROLE_CAN_WEAKEN_RULES')
            need(F.api(token,'POST',PREFIX+'/contents/forbidden-'+role+'.txt',{
                'branch':'main','message':'Synthetic forbidden direct push',
                'content':base64.b64encode(b'invented\n').decode()})[0] in (403,405), 'ROLE_CAN_PUSH_MAIN')
        checks.append('all-three-roles-denied-other-authorities-admin-protection-edit-and-main-push')
        need(F.api(tokens['mirror'],'POST',PREFIX+'/branches',{'old_branch_name':'main',
            'new_branch_name':'synthetic-delivery'})[0]==201,'MIRROR_BRANCH_FAILED')
        code,result=F.api(tokens['mirror'],'POST',PREFIX+'/contents/proposal.txt',{
            'branch':'synthetic-delivery','message':'Invented ordinary source',
            'content':base64.b64encode(b'invented proposal\n').decode()})
        need(code==201,'MIRROR_COMMIT_FAILED');head=result['commit']['sha']
        code,pr=F.api(tokens['mirror'],'POST',PREFIX+'/pulls',{'base':'main','head':'synthetic-delivery','title':'Invented proposal'})
        need(code==201,'MIRROR_PULL_FAILED');pull='/pulls/'+str(pr['number'])
        # A write collaborator can forge a green status. It MUST NOT be able
        # to get this merged without the separate review and merge roles.
        need(F.api(tokens['mirror'],'POST',PREFIX+'/statuses/'+head,{
            'context':R.CONTEXT,'state':'success','description':'Invented forged status'})[0]==201,'SYNTHETIC_STATUS_FAILED')
        merge={'Do':'fast-forward-only','head_commit_id':head,'force_merge':False}
        need(F.api(tokens['merge'],'POST',PREFIX+pull+'/merge',merge)[0] in (403,405), 'GREEN_WITHOUT_REVIEW_MERGED')
        code,_=F.api(tokens['merge'],'POST',PREFIX+pull+'/reviews',{'event':'APPROVED','commit_id':head,'body':'Invented non-authoritative review'})
        need(code in (200,201,403,422),'MERGER_REVIEW_UNEXPECTED')
        need(F.api(tokens['merge'],'POST',PREFIX+pull+'/merge',merge)[0] in (403,405),'MERGER_SELF_AUTHORIZED')
        checks.append('forged-status-and-merger-review-cannot-authorize-merge')
        need(F.api(tokens['review'],'POST',PREFIX+pull+'/reviews',{
            'event':'APPROVED','commit_id':head,'body':'Invented independent acceptance'})[0] in (200,201),'INDEPENDENT_REVIEW_FAILED')
        for role in ['mirror','review']:
            need(F.api(tokens[role],'POST',PREFIX+pull+'/merge',merge)[0] in (403,405),'NON_MERGER_CAN_MERGE')
        for _ in range(20):
            code,updated=F.api(admin,'GET',PREFIX+pull)
            if code==200 and updated.get('mergeable'):break
            time.sleep(0.2)
        need(F.api(tokens['merge'],'POST',PREFIX+pull+'/merge',merge)[0] in (200,201),'AUTHORIZED_MERGE_FAILED')
        code,branch=F.api(admin,'GET',PREFIX+'/branches/main')
        need(code==200 and branch['commit']['id']==head,'MAIN_RESULT_CHANGED')
        checks.append('independent-review-plus-designated-merger-fast-forwards-exact-head')
    Path('/var/lib/synthetic-forgejo-proof/delivery-roles.json').write_text(json.dumps({
        'schema_version':1,'checks':checks,'synthetic_only':True,'production_access':False}))

if __name__=='__main__':main()
