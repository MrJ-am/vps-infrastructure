"""Fast-forward the independently reviewed proposal through Forgejo protections."""
import http.client,importlib.util,json,os
HEAD='5a05461e9e3eb7cf77e99b85ae8d49630f13004d'
BASE='2a34dac722ff1dab9a63aec56e407dd996de0719'
PREFIX='/api/v1/repos/MrJ-am/mrjam-plateforme'
def require(ok,code):
    if not ok:raise RuntimeError(code)
def main():
    require(os.getuid()==0 and os.uname().nodename=='srv1982677','HOST_REFUSED')
    s=importlib.util.spec_from_file_location('bootstrap','/nix/store/8pkxq7pahlmhlmf6v890q2ica69cflsy-mrjam-forgejo-technical-bootstrap-1/libexec/core.py')
    B=importlib.util.module_from_spec(s);s.loader.exec_module(B)
    with B.governance_lease() as token:
        def api(method,suffix,body=None):
            c=http.client.HTTPConnection('127.0.0.1',3004,timeout=30)
            c.request(method,PREFIX+suffix,body=None if body is None else json.dumps(body),headers={'Host':'forge.mrj.am','Authorization':'token '+token,'Content-Type':'application/json'})
            r=c.getresponse();raw=r.read(1048577);status=r.status;c.close()
            require(len(raw)<=1048576 and status in (200,201,204),'PROTECTED_API_REFUSED')
            return json.loads(raw) if raw else None
        protection=api('GET','/branch_protections/main')
        require(protection['required_approvals']==1 and protection['enable_status_check'] and protection['status_check_contexts']==['mrjam/independent-validation'] and protection['apply_to_admins'],'PROTECTION_REFUSED')
        pr=api('GET','/pulls/1')
        require(pr['head']['sha']==HEAD and pr['base']['ref']=='main','PROPOSAL_CHANGED')
        reviews=api('GET','/pulls/1/reviews')
        require(any(r['user']['id']==1 and r['user']['login']=='MrJam' and r['state']=='APPROVED' and r['commit_id']==HEAD and r['official'] and not r['stale'] and not r['dismissed'] for r in reviews),'HUMAN_REVIEW_REQUIRED')
        if not pr['merged']:
            require(pr['state']=='open' and pr['mergeable'] and api('GET','/branches/main')['commit']['id']==BASE,'BASE_MOVED')
            api('POST','/pulls/1/merge',{'Do':'fast-forward-only','head_commit_id':HEAD,'force_merge':False,'merge_when_checks_succeed':False,'delete_branch_after_merge':False})
        pr=api('GET','/pulls/1')
        require(pr['merged'] and api('GET','/branches/main')['commit']['id']==HEAD,'MERGE_NOT_CONFIRMED')
        require(api('GET','/branch_protections/main')==protection,'PROTECTION_CHANGED')
    print(json.dumps({'code':'REVIEWED_SOURCE_FAST_FORWARDED','head':HEAD,'reviewer':'MrJam','review_id':3,'protected_merge':True,'protection_unchanged':True,'temporary_token_revoked':True,'application_deployed':False}))
if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps({'code':str(error) if isinstance(error,RuntimeError) else 'MERGE_FAILED','exception_type':type(error).__name__}));raise SystemExit(2)
