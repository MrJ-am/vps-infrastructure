"""Invented Forgejo guest setup/tests only. Not included in the backend package."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.request

PACKAGE=Path(os.environ['SYNTHETIC_PROPOSAL_PACKAGE'])
SEED=Path(os.environ['SYNTHETIC_PROPOSAL_SEED'])
sys.path.insert(0,str(PACKAGE/'libexec'))
import core
import lease
import credentials
import reconcile
spec=importlib.util.spec_from_file_location('old_fixture','/etc/forgejo-bootstrap-fixture.py')
old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
bootstrap=old.core
BINDING=Path(os.environ['SYNTHETIC_PROPOSAL_BINDING'])
binding=core.Binding(BINDING.read_bytes(),hashlib.sha256(BINDING.read_bytes()).hexdigest())
git=core.Git(os.environ['SYNTHETIC_GIT'],str(PACKAGE/'bin/mrjam-rules-proposal-credential'),str(PACKAGE/'hooks'),binding)


def require(value,code):
    if not value:raise RuntimeError(code)


def api(token,method,path,value=None):
    request=urllib.request.Request('http://127.0.0.1:3004'+path,
        data=None if value is None else json.dumps(value).encode(),method=method,
        headers={'Authorization':'token '+token,'Content-Type':'application/json','Host':'forge.mrj.am'})
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),bootstrap.NoRedirect())
    try:
        with opener.open(request,timeout=5) as response:
            raw=response.read(131073);require(len(raw)<=131072,'FIXTURE_API_BOUND')
            return response.status,json.loads(raw) if raw else None
    except urllib.error.HTTPError as error:
        code=error.code;error.close();return code,None


def no_lease():
    require(old.sql("SELECT count(*) FROM access_token WHERE name LIKE 'mrjam-rules-proposal-%'")=='0','LEASE_TOKEN_RETAINED')
    require(old.sql('SELECT count(*) FROM access_token_resource_repo r LEFT JOIN access_token t ON t.id=r.token_id WHERE t.id IS NULL')=='0','LEASE_RESOURCE_ORPHAN')
    require(not (bootstrap.STATE/lease.JOURNAL).exists(),'LEASE_JOURNAL_RETAINED')


def prepare():
    with bootstrap.governance_lease() as token:
        require(api(token,'POST','/api/v1/orgs',{'username':'MrJ-am','visibility':'private'})[0]==201,'CREATE_ORG')
        for name in ('mrjam-validation','synthetic-unrelated'):
            require(api(token,'POST','/api/v1/orgs/MrJ-am/repos',{'name':name,'private':True,'auto_init':False,'default_branch':'main'})[0]==201,'CREATE_REPO')
        seed=Path('/var/lib/synthetic-forgejo-proof/seed.git')
        git.command(['init','--bare',str(seed)])
        git.command(['-C',str(seed),'fetch',str(SEED/'baseline.bundle'),'refs/heads/main:refs/heads/main'])
        with credentials.broker(token,'mrjam-validation'):
            # Fixture's initial source import predates protection. Production
            # always uses the immutable create-only hook instead.
            args=['-c','core.hooksPath=/dev/null','-C',str(seed),'push',core.URL,'refs/heads/main:refs/heads/main']
            git.command(args)
        for attempt in range(60):
            if api(token,'GET',core.BASE)[1]['empty'] is False:
                break
            time.sleep(0.25)
        else:
            raise RuntimeError('FIXTURE_POST_RECEIVE_DID_NOT_FINISH')
        require(api(token,'POST',core.BASE+'/branch_protections',reconcile.desired_protection())[0]==201,'PROTECT_MAIN')
    core.STATE.mkdir(mode=0o700)
    core.INPUT.write_bytes((SEED/'proposal.bundle').read_bytes());core.INPUT.chmod(0o600)
    # An unrelated resource-bound token must survive this helper's cleanup.
    old.cli('admin','user','generate-access-token','--username',lease.ACCOUNT,'--token-name','synthetic-untouched',
        '--scopes','read:repository','--raw')
    old.sql("INSERT INTO access_token_resource_repo(token_id,repo_id,created_unix) SELECT t.id,r.id,1 FROM access_token t CROSS JOIN repository r WHERE t.name='synthetic-untouched' AND r.lower_name='synthetic-unrelated'; UPDATE access_token SET resource_all_repos=false WHERE name='synthetic-untouched'")
    no_lease()


def scoped():
    original_sql = lease.sql
    def diagnosed_sql(bootstrap_arg, operation, label):
        try:
            return original_sql(bootstrap_arg, operation, label)
        except Exception:
            if operation == 'restrict':
                # Synthetic fixture only: boolean predicates, never token text.
                require(lease.LABEL.fullmatch(label), 'FIXTURE_LABEL')
                token = lease.SELECT_TOKEN.replace(":'lease'", "'"+label+"'")
                predicates = {
                    'token_unique': '(SELECT count(*)=1 FROM ('+token+') t)',
                    'repository_eligible': '(SELECT count(*)=1 FROM ('+lease.SELECT_REPO+') r)',
                    'fresh_all_repositories': '(SELECT bool_and(resource_all_repos) FROM access_token WHERE id IN ('+token+'))',
                    'scope_exact': "(SELECT bool_and(string_to_array(scope,',') @> ARRAY['read:user','write:repository'] AND cardinality(string_to_array(scope,','))=2) FROM access_token WHERE id IN ("+token+'))',
                    'resources_empty': 'NOT EXISTS(SELECT FROM access_token_resource_repo WHERE token_id IN ('+token+'))',
                    'repository_nonempty': "(SELECT bool_and(NOT is_empty) FROM repository WHERE lower_name='mrjam-validation')",
                }
                print(json.dumps({key: old.sql('SELECT '+predicate) == 't' for key,predicate in predicates.items()},sort_keys=True),flush=True)
            raise
    lease.sql = diagnosed_sql
    with lease.repository_lease(bootstrap) as token:
        require(api(token,'GET',core.BASE)[0]==200,'SCOPED_REPOSITORY_INACCESSIBLE')
        require(api(token,'GET',core.BASE+'/branch_protections/main')[0]==403,'ADMIN_OVERRIDE_WAS_NOT_REDUCED')
        require(api(token,'GET','/api/v1/repos/MrJ-am/synthetic-unrelated')[0] in (403,404),'OTHER_PRIVATE_REPOSITORY_ACCESSIBLE')
        require(api(token,'GET','/api/v1/orgs/MrJ-am')[0]==403,'ORGANIZATION_SCOPE_PRESENT')
        require(old.sql("SELECT count(*) FROM access_token t JOIN access_token_resource_repo a ON a.token_id=t.id JOIN repository r ON r.id=a.repo_id WHERE t.name LIKE 'mrjam-rules-proposal-%' AND NOT t.resource_all_repos AND r.lower_name='mrjam-validation'")=='1','RESOURCE_BINDING_NOT_EXACT')
    no_lease()
    require(old.sql("SELECT count(*) FROM access_token t JOIN access_token_resource_repo a ON a.token_id=t.id WHERE t.name='synthetic-untouched'")=='1','UNRELATED_TOKEN_CHANGED')


def protection_guard():
    import protection
    require(protection.verify(bootstrap), 'PROTECTION_GUARD_BASELINE')
    repo_id = int(old.sql("SELECT id FROM repository WHERE lower_name='mrjam-validation'"))
    original = json.loads(old.sql('SELECT to_jsonb(p)::text FROM protected_branch p WHERE repo_id='+str(repo_id)))
    columns = ('can_push','enable_whitelist','whitelist_deploy_keys','enable_merge_whitelist',
        'enable_status_check','enable_approvals_whitelist','block_on_rejected_reviews',
        'block_on_official_review_requests','block_on_outdated_branch','dismiss_stale_approvals',
        'ignore_stale_approvals','require_signed_commits','apply_to_admins','required_approvals',
        'branch_name','protected_file_patterns','unprotected_file_patterns','status_check_contexts',
        'whitelist_user_i_ds','whitelist_team_i_ds','merge_whitelist_user_i_ds','merge_whitelist_team_i_ds',
        'approvals_whitelist_user_i_ds','approvals_whitelist_team_i_ds')
    def literal(value):
        if value is None:return 'NULL'
        if type(value) is bool:return 'true' if value else 'false'
        if type(value) is int:return str(value)
        return "'"+str(value).replace("'","''")+"'"
    for column in columns:
        previous = original[column]
        if type(previous) is bool:following = not previous
        elif type(previous) is int:following = previous+1
        elif column.endswith('_i_ds'):following = '[1]'
        elif column == 'status_check_contexts':following = '["invented-other-context"]'
        else:following = 'invented-drift'
        try:
            old.sql('UPDATE protected_branch SET '+column+'='+literal(following)+' WHERE repo_id='+str(repo_id))
            try:protection.verify(bootstrap)
            except lease.Refused as error:require(str(error)=='MAIN_PROTECTION_REFUSED','WRONG_PROTECTION_REFUSAL')
            else:raise RuntimeError('PROTECTION_DRIFT_ACCEPTED')
        finally:
            old.sql('UPDATE protected_branch SET '+column+'='+literal(previous)+' WHERE repo_id='+str(repo_id))
    try:
        old.sql("INSERT INTO protected_branch(repo_id,branch_name) VALUES ("+str(repo_id)+",'invented*')")
        try:protection.verify(bootstrap)
        except lease.Refused:pass
        else:raise RuntimeError('EXTRA_PROTECTION_ACCEPTED')
    finally:
        old.sql("DELETE FROM protected_branch WHERE repo_id="+str(repo_id)+" AND branch_name='invented*'")
    require(protection.verify(bootstrap),'PROTECTION_GUARD_RESTORED')


def open_pr():
    result=core.open_proposal(binding,git,bootstrap)
    require(result['code']=='RULES_PROPOSAL_OPENED' and result['branch_created'] and result['pull_request_created'],'PROPOSAL_NOT_CREATED')
    require(not any(result[x] for x in ('main_changed','protection_changed','review_created','status_created','merged','actions_activated')),'UNAUTHORIZED_EFFECT')
    Path('/var/lib/synthetic-forgejo-proof/proposal-result.json').write_text(json.dumps(result))
    no_lease()


def replay():
    before=json.loads(Path('/var/lib/synthetic-forgejo-proof/proposal-result.json').read_text())
    after=core.open_proposal(binding,git,bootstrap)
    require(after==before|{'branch_created':False,'pull_request_created':False},'IDEMPOTENCE_REFUSED')
    no_lease()


def protected():
    with lease.repository_lease(bootstrap) as token:
        with credentials.broker(token,'mrjam-validation'):
            p=Path('/var/lib/synthetic-forgejo-proof/attempt.git')
            git.command(['init','--bare',str(p)])
            git.command(['-C',str(p),'fetch',core.URL,binding.ref+':refs/heads/proposal'])
            try:
                git.command(['-c','core.hooksPath=/dev/null','-C',str(p),'push',core.URL,binding.value['head']+':refs/heads/main'])
            except core.Refused:
                pass
            else:
                raise RuntimeError('PROTECTED_MAIN_BYPASSED')
            require(git.refs()['refs/heads/main']==binding.value['base'],'MAIN_CHANGED')
        core.observe(core.Transport(token,binding),binding,bootstrap)
    no_lease()
    require(old.sql('SELECT count(*) FROM review')=='0','REVIEW_CREATED')
    require(old.sql('SELECT count(*) FROM commit_status')=='0','STATUS_CREATED')


def projection():
    # Exact GET-only parent-owned modules, using only this invented guest PR.
    sys.path.insert(0,'/etc/review-projection-fixture')
    import api_projection, read_transport, contract
    record=json.loads(Path('/var/lib/synthetic-forgejo-proof/proposal-result.json').read_text())
    captured={}
    with lease.repository_lease(bootstrap) as token:
        transport=read_transport.Transport(token,'mrjam-validation',record['pull_request'])
        class Capture:
            def get(self,path):
                result=transport.get(path);captured[path]={'value':result[0],'headers':result[1]};return result
        reader=Capture();repo,_=reader.get(core.BASE);me,_=reader.get('/api/v1/user')
        now=int(time.time());generation='/nix/store/'+'0'*32+'-invented-generation'
        policy={'schema_version':1,'scope':'mrjam-forgejo-review-policy-v1','repository':'mrjam-validation',
            'repository_id':repo['id'],'source_id':'rules','reviewer_ids':[int(old.sql("SELECT id FROM public.\"user\" WHERE lower_name='mrjam'"))],
            'technical_ids':[me['id']],'merge_actor_id':me['id'],'validation_policy_sha256':'a'*64,
            'target':'srv1982677','previous_generation':generation,'not_before':now-60,'expires_at':now+3600}
        try:
            api_projection.collect(reader,policy,record['pull_request'],generation,now=now)
        except contract.Refused as error:
            code=str(error)
        else:
            raise RuntimeError('EMPTY_REVIEW_WAS_ACCEPTED')
        require(code=='REVIEWS_REFUSED','NATIVE_API_PROJECTION_MISMATCH')
    no_lease()
    Path('/var/lib/synthetic-forgejo-proof/api-projection.json').write_text(json.dumps({
        'schema_version':1,'scope':'invented-guest-api-responses-only','review_refusal':code,
        'policy':policy,'responses':captured},sort_keys=True)+'\n')


def refusal():
    raw=core.INPUT.read_bytes();core.INPUT.write_bytes(raw+b'changed')
    try:
        try:core.open_proposal(binding,git,bootstrap)
        except core.Refused as error:require(str(error)=='PROPOSAL_BUNDLE_REFUSED','WRONG_TAMPER_REFUSAL')
        else:raise RuntimeError('TAMPER_ACCEPTED')
    finally:core.INPUT.write_bytes(raw)
    no_lease()
    record=json.loads(Path('/var/lib/synthetic-forgejo-proof/proposal-result.json').read_text())
    with bootstrap.governance_lease() as token:
        require(api(token,'PATCH',core.BASE+'/pulls/'+str(record['pull_request']),{'body':'invented independent edit'})[0] in (200,201),'FIXTURE_PR_EDIT')
    try:core.open_proposal(binding,git,bootstrap)
    except core.Refused as error:require(str(error)=='PULL_REQUEST_CONFLICT','WRONG_PR_REFUSAL')
    else:raise RuntimeError('CHANGED_PR_ACCEPTED')
    no_lease()
    with bootstrap.governance_lease() as token:
        require(api(token,'GET',core.BASE+'/pulls/'+str(record['pull_request']))[1]['body']=='invented independent edit','PR_EDIT_OVERWRITTEN')


if __name__=='__main__':
    {'prepare':prepare,'scoped':scoped,'protection':protection_guard,'open':open_pr,'replay':replay,'protected':protected,'projection':projection,'refusal':refusal}[sys.argv[1]]()
    print('SYNTHETIC_RULES_PROPOSAL_CHECK_PASSED')
