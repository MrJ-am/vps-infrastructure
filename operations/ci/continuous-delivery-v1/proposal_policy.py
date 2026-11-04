"""Independently check intake output before constructing an admission.

`observed` is fresh commit/tree metadata obtained by the protected caller,
never the intake receipt. No signing key or candidate command is used here.
"""
import copy,hashlib
from pathlib import Path,PurePosixPath
import source_snapshot as S
from proposal_prepare import encode

def verify(root,base_policy,proposed,observed,proposal,*,validator_policy,gate_path):
    P=validator_policy;P.checked_policy(base_policy);P.checked_policy(proposed)
    S.require(type(observed) is dict and observed,'FRESH_SOURCE_OBSERVATION_REQUIRED')
    base_sources={s['id']:s for s in base_policy['sources']}
    S.require(set(observed)<=set(base_sources),'OBSERVED_SOURCE_SCOPE_REFUSED')
    expected=copy.deepcopy(base_policy)
    for source in expected['sources']:
        if source['id'] not in observed:continue
        binding=observed[source['id']]
        S.require(type(binding) is dict and set(binding)=={'repository','revision','tree_sha'}
                  and binding['repository']==source['repository'],'OBSERVED_SOURCE_IDENTITY_REFUSED')
        for key in ('revision','tree_sha'):
            S.require(type(binding[key]) is str and S.OID.fullmatch(binding[key]),'OBSERVED_SOURCE_SHA_REFUSED')
            source[key]=binding[key]
    root=Path(root);sources={s['id']:s for s in expected['sources']}
    for name in expected['rust_manifests']:
        parts=PurePosixPath(name).parts
        path=root/sources[parts[1]]['root']/PurePosixPath(*parts[2:]) if parts[0]=='components' else root/sources['platform']['root']/name
        S.require(path.is_file() and not path.is_symlink() and path.stat().st_size<=4*1024**2,'RUST_MANIFEST_REFUSED')
        expected['rust_manifests'][name]=P.sha(path)
    S.require(proposed==expected,'INTAKE_POLICY_CHANGED')
    identities=encode({'schema_version':1,'rules_revision':expected['rules_revision'],
        'sources':[{k:source[k] for k in ('id','repository','revision','tree_sha')} for source in expected['sources']]})
    path=root/'source-bindings.json'
    S.require(path.is_file() and not path.is_symlink() and path.stat().st_size==len(identities)
              and path.read_bytes()==identities,'SOURCE_IDENTITIES_REFUSED')
    _,digest=P.verify_sources(root,expected,gate_path)
    S.require(digest==proposal,'PROPOSAL_DIGEST_REFUSED')
    return expected
