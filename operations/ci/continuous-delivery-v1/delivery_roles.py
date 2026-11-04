"""Closed roles and restrictive Forgejo protection plan for ordinary delivery.

Planning alone creates no account, grants no access and changes no protection.
The validation and infrastructure repositories are deliberately outside these
roles. A later protected installer must verify the actual ACLs and refusals.
"""
from source_snapshot import require

APPLICATIONS=('Signature','apprendre-a-demontrer','etp-vie-affective','matheval',
    'mrjam-plateforme','style-mrjam','vision')
ROLES={'mirror':'mrjam-proposal-mirror','review':'mrjam-validation-review',
    'merge':'mrjam-release-merge'}
HUMAN='MrJam'
CONTEXT='mrjam/independent-validation'

def protection_change(repository,observed):
    require(repository in APPLICATIONS,'DELIVERY_REPOSITORY_REFUSED')
    require(type(observed) is dict and observed.get('branch_name')=='main'
        and observed.get('rule_name')=='main','DELIVERY_BRANCH_REFUSED')
    required={'enable_push':False,'enable_status_check':True,'status_check_contexts':[CONTEXT],
        'required_approvals':1,'block_on_rejected_reviews':True,
        'block_on_official_review_requests':True,'block_on_outdated_branch':True,
        'dismiss_stale_approvals':True,'apply_to_admins':True}
    require(all(observed.get(k)==v for k,v in required.items()),'DELIVERY_EXISTING_GATES_REFUSED')
    desired={'enable_merge_whitelist':True,'merge_whitelist_usernames':[HUMAN,ROLES['merge']],
        'merge_whitelist_teams':[],'enable_approvals_whitelist':True,
        'approvals_whitelist_username':[HUMAN,ROLES['review']],'approvals_whitelist_teams':[]}
    # A pre-existing restriction is not silently expanded or replaced. The
    # installer can resume our exact adopted restriction, or restrict the
    # original unrestricted policy. Any other governance requires resolution.
    for enabled,users,teams in [('enable_merge_whitelist','merge_whitelist_usernames','merge_whitelist_teams'),
            ('enable_approvals_whitelist','approvals_whitelist_username','approvals_whitelist_teams')]:
        require(type(observed.get(enabled)) is bool and type(observed.get(users)) is list
            and type(observed.get(teams)) is list,'DELIVERY_WHITELIST_FIELDS_REFUSED')
        require((observed[enabled] is False and observed[users]==[] and observed[teams]==[])
            or (observed[enabled] is True and sorted(observed[users])==sorted(desired[users])
                and observed[teams]==[]),'DELIVERY_EXISTING_RESTRICTION_REFUSED')
    return desired

def verify_protection(before,after,change):
    require(type(after) is dict and set(after)==set(before),'DELIVERY_PROTECTION_FIELDS_CHANGED')
    require(all(after[k]==v if not isinstance(v,list) else sorted(after[k])==sorted(v)
        for k,v in change.items()),'DELIVERY_RESTRICTION_NOT_ADOPTED')
    require(all(after[k]==before[k] for k in before if k not in change and k!='updated_at'),
        'DELIVERY_OTHER_GATES_CHANGED')

def verify_acl(role,account,collaborations):
    require(role in ROLES and type(account) is dict and account=={
        'name':ROLES[role],'eligible':True,'organization_memberships':0,'owned_repositories':0},
        'DELIVERY_ACCOUNT_REFUSED')
    require(type(collaborations) is list and sorted(collaborations,key=lambda x:(x['owner'],x['repo']))==
        [{'owner':'MrJ-am','repo':name,'permission':2} for name in sorted(APPLICATIONS)],
        'DELIVERY_ACL_REFUSED')
