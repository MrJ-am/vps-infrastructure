"""Read-only final checks around a future bounded merge, never a merger.

These observations are not atomic with Forgejo writes. A changed or withdrawn
review after a merge withholds a delivery decision; it does not undo Git history.
"""
import contract as V
import review_contract_v2 as R
import api_projection_v2 as A


def selected_review(api, policy, binding, *, now):
    R.policy(policy)
    V.require(binding['repository_id']==policy['repository_id'], 'REVIEW_TARGET_REFUSED')
    for key in ('pull_request','review_id','reviewer_id'):R.identifier(binding[key])
    root='/api/v1/repos/MrJ-am/'+policy['repository']
    raw,_=api.get(root+'/pulls/'+str(binding['pull_request'])+'/reviews/'+str(binding['review_id']))
    row=A.review_projection(raw)
    V.require(row['id']==binding['review_id'] and row['reviewer_id']==binding['reviewer_id']
        and row['reviewer_id'] in policy['reviewer_ids'] and row['reviewer_id'] not in policy['technical_ids']
        and row['state']=='APPROVED' and row['official'] is True
        and row['stale'] is False and row['dismissed'] is False
        and row['commit_id']==binding['head_sha']
        and row['updated_at']==binding['review_updated_at']<=now
        and row['body']==R.approval_text(policy['repository'],binding['pull_request'],binding['head_sha'],binding['manifest_sha256']),
        'SELECTED_REVIEW_CHANGED')


def before_merge(api, envelope, validation_policy, review_policy, binding, manifest, *, now, executable):
    """Refresh all review pages, validate the signature, then reread chosen review."""
    observed=A.collect(api,review_policy,binding['pull_request'],binding['previous_generation'],now=now)
    fresh=R.bind_review(envelope,validation_policy,review_policy,observed,manifest,now=now,executable=executable)
    V.require(type(binding) is dict and set(binding)==set(fresh),'REVIEW_BINDING_REFUSED')
    V.integer(binding['expires_at'],now+1,2**63-1)
    V.integer(binding['observed_at'],0,now)
    V.require(all(binding[k]==fresh[k] for k in fresh if k not in ('observed_at','expires_at')),'REVIEW_BINDING_CHANGED')
    selected_review(api,review_policy,fresh,now=now)
    return fresh


def after_merge(api, review_policy, binding, *, now):
    """Confirm expected fast-forward and unchanged selected approval only.

    Caller must already hold a verified binding from before_merge. This function
    grants no authority and does not reverify validation signatures, protection,
    other reviews, deployed generation, artifact files or credentials.
    """
    R.policy(review_policy)
    V.integer(now,review_policy['not_before'],review_policy['expires_at']-1)
    V.integer(binding['expires_at'],now+1,2**63-1)
    V.require(binding['review_policy_sha256']==V.sha(V.canonical(review_policy)), 'REVIEW_POLICY_CHANGED')
    root='/api/v1/repos/MrJ-am/'+review_policy['repository']
    raw,_=api.get(root+'/pulls/'+str(binding['pull_request']))
    pull=A.pull_projection(raw,review_policy)
    V.require(pull['pull_request']==binding['pull_request'] and pull['state']=='closed'
        and pull['draft'] is False and pull['merged'] is True and pull['base_ref']=='main'
        and pull['head_sha']==binding['head_sha'] and binding['reviewer_id'] in pull['requested_reviewer_ids']
        and A.revision(raw['merge_commit_sha'])==binding['head_sha'], 'MERGE_RESULT_REFUSED')
    branch,_=api.get(root+'/branches/main')
    V.require(A.revision(A.record(A.record(branch)['commit'])['id'])==binding['head_sha'],'MERGED_MAIN_CHANGED')
    selected_review(api,review_policy,binding,now=now)
    return {'schema_version':1,'scope':'mrjam-postmerge-observation-v1',
        'head_sha':binding['head_sha'],'review_id':binding['review_id'],'observed_at':now}
