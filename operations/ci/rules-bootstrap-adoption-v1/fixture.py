"""Invented guest identities and native reviews only; never installed in helper."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

spec=importlib.util.spec_from_file_location('proposal_fixture','/etc/rules-proposal-fixture.py')
F=importlib.util.module_from_spec(spec);spec.loader.exec_module(F)
sys.path.insert(0,str(Path(os.environ['SYNTHETIC_ADOPTION_PACKAGE'])/'libexec'))
import adoption
import identity
import sso
import api_projection

sql=F.old.sql
SUBJECT='00000000-0000-4000-8000-000000000001'
ROOT=Path('/var/lib/synthetic-forgejo-proof')


def require(value,code):
    if not value:raise RuntimeError(code)


def setup_identity():
    folder=Path('/var/lib/forgejo-identity');folder.mkdir(mode=0o700)
    file=folder/'client.json';file.write_text(json.dumps({'clientId':'mrjam-forgejo',
        'clientSecret':'SYNTHETIC-OIDC-SECRET-NOT-PRODUCTION','ownerSubject':SUBJECT}));file.chmod(0o600)
    parameters=json.dumps({'Provider':'openidConnect','ClientID':'mrjam-forgejo',
        'ClientSecret':'SYNTHETIC-OIDC-SECRET-NOT-PRODUCTION','OpenIDConnectAutoDiscoveryURL':sso.DISCOVERY})
    sql("INSERT INTO login_source(id,type,name,is_active,cfg,created_unix,updated_unix) VALUES(999,6,'Kanidm',true,'"+parameters+"',1,1)")
    sql("UPDATE public.\"user\" SET login_type=6,login_source=999,login_name='"+SUBJECT+"' WHERE lower_name='mrjam'")
    try:identity.owner(F.bootstrap)
    except identity.Refused:pass
    else:raise RuntimeError('AMBIGUOUS_OWNER_ACCEPTED')
    # Only this invented fixture resolves its deliberate legacy ambiguity.
    sql("UPDATE public.\"user\" SET name='invented-other',lower_name='invented-other' WHERE lower_name='mrjam-admin'")
    require(identity.owner(F.bootstrap)==int(sql("SELECT id FROM public.\"user\" WHERE lower_name='mrjam'")),'WRONG_SSO_OWNER')
    sql("UPDATE login_source SET is_active=false WHERE id=999")
    try:
        try:identity.owner(F.bootstrap)
        except identity.Refused:pass
        else:raise RuntimeError('INACTIVE_PROVIDER_ACCEPTED')
    finally:sql("UPDATE login_source SET is_active=true WHERE id=999")
    require(identity.owner(F.bootstrap)>0,'SSO_NOT_RESTORED')


def missing():
    try:adoption.adopt(F.binding,F.git,F.bootstrap)
    except adoption.Refused as error:require(str(error)=='HUMAN_REVIEW_REQUIRED','WRONG_NO_REVIEW_REFUSAL')
    else:raise RuntimeError('ABSENT_REVIEW_ACCEPTED')
    require(not (F.core.STATE/adoption.Journal.NAME).exists(),'PREMATURE_CHECKPOINT')
    with F.lease.repository_lease(F.bootstrap) as token:
        with F.credentials.broker(token,F.core.REPO):
            require(F.git.refs()['refs/heads/main']==F.binding.value['base'],'MAIN_CHANGED_WITHOUT_REVIEW')
    F.no_lease()


def review():
    # This token belongs only to the invented guest human analogue; production
    # helper has no route to create reviews and never mints this token.
    token=F.old.cli('admin','user','generate-access-token','--username','MrJam',
        '--token-name','synthetic-review-only','--scopes','read:user,write:repository','--raw').decode().strip()
    try:
        status,tree=F.api(token,'GET',adoption.ROOT+'/git/trees/'+F.binding.value['head']+'%5E%7Btree%7D?page=1&per_page=1')
        require(status==200 and tree['sha']==F.binding.value['tree'],'EXPLICIT_TREE_RESOLUTION_MISMATCH')
        (ROOT/'explicit-tree-resolution.json').write_text(json.dumps({'schema_version':1,
            'head':F.binding.value['head'],'expected_git_tree':F.binding.value['tree'],
            'api_resolved_tree':tree['sha'],'matched':True,'synthetic_fixture_only':True}))
        status,row=F.api(token,'POST',adoption.PULL+'/reviews',{'event':'APPROVED',
            'body':' \r\n'+adoption.TEXT+'\r\n ','commit_id':F.binding.value['head']})
        require(status==200,'NATIVE_REVIEW_CREATE_REFUSED')
        projected=api_projection.review_projection(row)
        require(projected['reviewer_id']==identity.owner(F.bootstrap) and projected['official'] is True
            and projected['state']=='APPROVED' and projected['commit_id']==F.binding.value['head'],
            'NATIVE_REVIEW_SHAPE_MISMATCH')
        (ROOT/'bootstrap-review.json').write_text(json.dumps(row))
        status,pull=F.api(token,'GET',adoption.PULL)
        require(status==200 and [r['id'] for r in pull['requested_reviewers']]==[row['user']['id']],
            'NATIVE_APPROVED_PARTICIPANT_MISMATCH')
        (ROOT/'native-review-participants.json').write_text(json.dumps({'schema_version':1,
            'approval_in_requested_reviewers':True,'requested_reviewers_count':1,
            'review_state':'APPROVED','synthetic_fixture_only':True}))
    finally:
        sql("DELETE FROM access_token WHERE name='synthetic-review-only'")
    require(sql('SELECT count(*) FROM commit_status')=='0','STATUS_CREATED')


def adopt():
    result=adoption.adopt(F.binding,F.git,F.bootstrap)
    require(result['code']=='RULES_BOOTSTRAP_MERGED_REVIEW_RECHECKED','NATIVE_BOOTSTRAP_MERGE_FAILED')
    require(not any(result[k] for k in ('protection_changed','status_created','review_created','ci_attestation_issued','activation_performed')),'UNAUTHORIZED_BOOTSTRAP_EFFECT')
    require(sql('SELECT count(*) FROM commit_status')=='0','STATUS_CREATED')
    require(sql('SELECT count(*) FROM review')=='1','EXTRA_REVIEW_CREATED')
    (ROOT/'bootstrap-adoption-result.json').write_text(json.dumps(result))
    F.no_lease()


def replay():
    before=(F.core.STATE/adoption.Journal.NAME).read_bytes()
    result=adoption.adopt(F.binding,F.git,F.bootstrap)
    require(result==json.loads((ROOT/'bootstrap-adoption-result.json').read_text()),'ADOPTION_REPLAY_CHANGED')
    require((F.core.STATE/adoption.Journal.NAME).read_bytes()==before,'CHECKPOINT_CONTENT_CHANGED')
    require(sql('SELECT count(*) FROM commit_status')=='0' and sql('SELECT count(*) FROM review')=='1','EXTRA_STATUS_REVIEW')
    F.no_lease()


if __name__=='__main__':
    {'identity':setup_identity,'missing':missing,'review':review,'adopt':adopt,'replay':replay}[sys.argv[1]]()
    print('SYNTHETIC_BOOTSTRAP_ADOPTION_CHECK_PASSED')
