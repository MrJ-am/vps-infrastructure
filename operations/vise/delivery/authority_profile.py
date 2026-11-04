"""Additional ViSe authority bindings, not a signer or an adoption bypass.

The caller supplies the installed contract and independently pinned rules
revision. Registry/credential/producer checks and signature verification
remain mandatory. No candidate selects the anchor or this module.
"""
import hashlib,json
import source_policy as P

REQUIRED_STEPS=(
    'complete-vise-source-tree',
    'locked-toolchain-versions',
    'locked-cargo-npm-elm-dependencies',
    'rust-offline-release-build',
    'typescript-no-emit',
    'vise-frontend-build',
    'vise-component-tests',
    'vise-api-tests-synthetic-postgresql',
    'vise-schema-and-role-refusals',
    'vise-graceful-stop-and-restart',
    'vise-restore-current-erasure-ledger',
    'vise-artifact-content-bound',
)
NOT_ESTABLISHED=(
    'Independent release acceptance is not established by this content report.',
    'Production deployment is not authorized by this content report.',
    'No production database, erasure ledger or backup was used in validation.',
)


def expected_steps(authority,report_policy_bytes,*,contract,rules_revision):
    contract.policy(authority)
    P.require(type(report_policy_bytes) is bytes and 0<len(report_policy_bytes)<=131072,'VISE_REPORT_POLICY_LIMIT')
    policy=P.checked_policy(json.loads(report_policy_bytes,object_pairs_hook=P.pairs))
    P.require(type(rules_revision) is str and P.HEX40.fullmatch(rules_revision)
        and policy['rules_revision']==authority['rules_revision']==rules_revision,'VISE_AUTHORITY_RULES_REFUSED')
    P.require(hashlib.sha256(report_policy_bytes).hexdigest()==authority['report_policy_sha256'],
        'VISE_AUTHORITY_POLICY_BINDING_REFUSED')
    P.require(authority['sources']==[{k:s[k] for k in ['id','repository','revision','tree_sha']}
        for s in policy['sources']],'VISE_AUTHORITY_SOURCE_BINDING_REFUSED')
    P.require(authority['required_steps']==list(REQUIRED_STEPS),'VISE_AUTHORITY_STEPS_REFUSED')
    P.require(authority['not_established']==list(NOT_ESTABLISHED),'VISE_AUTHORITY_LIMITS_REFUSED')
    return [{'name':name,'status':'passed'} for name in REQUIRED_STEPS]
