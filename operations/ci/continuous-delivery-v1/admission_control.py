"""Installed trust anchor and root registry; no caller-selected policy paths."""
import contract as C
import admission_registry as R

ANCHOR_PATH='@admission-anchor@'
BUBBLEWRAP='@admission-bubblewrap@'
PROFILE='platform'
EXTRA_ANCHORS={}

def record_profile(record):
    binding=record['files']['details']
    raw=R.metadata_bytes(binding['path'])
    C.require(C.sha(raw)==binding['sha256'],'ADMISSION_CONTENT_CHANGED')
    details=C.parse(raw)
    C.require(type(details.get('schema_version')) is int,'ADMISSION_PROFILE_REFUSED')
    if details['schema_version']==1:return 'platform'
    C.require(details['schema_version']==2 and details.get('profile')=='vise-v1',
              'ADMISSION_PROFILE_REFUSED')
    return 'vise-v1'

def anchor_for(profile):
    baseline=C.policy(C.parse(R.store_bytes(ANCHOR_PATH)))
    if profile==PROFILE:return baseline
    C.require(profile in ('platform','vise-v1') and profile in EXTRA_ANCHORS,
              'ADMISSION_PROFILE_NOT_INSTALLED')
    path=EXTRA_ANCHORS[profile];C.text(path,C.STORE)
    selected=C.policy(C.parse(R.store_bytes(path)))
    # Shared daemons retain their installed identities and implementation.
    # Rules and required steps may differ only through this installed anchor.
    for field in ('collector_uid','signer_uid','requester_uid','key_id','public_key_der'):
        C.require(selected[field]==baseline[field],'ADMISSION_PROFILE_IDENTITY_CHANGED')
    for field in R.RECIPE_FIELDS:
        C.require(selected['producer'][field]==baseline['producer'][field],
                  'ADMISSION_PROFILE_RECIPE_CHANGED')
    return selected

def load(proposal):
    record=R.entry(proposal)
    profile=record_profile(record)
    selected=R.resolve(record,proposal,anchor_for(profile),BUBBLEWRAP,read=R.metadata_bytes,profile=profile)
    selected['worker_path']=record['files']['worker']['path']
    return selected

def expected_steps(value):
    C.require(len(value['accepted_proposals'])==1,'ADMISSION_SCOPE_REFUSED')
    selected=load(value['accepted_proposals'][0])
    C.require(selected['authority']==value,'ADMISSION_CHANGED')
    if selected['details'].get('profile')=='vise-v1':
        return [{'name':name,'status':'passed'} for name in value['required_steps']]
    entry=selected['details']['selected_entry']
    return [({'name':name,'status':'passed','base_sha256':entry['base_sha256'],
              'corrected_sha256':entry['corrected_sha256']}
             if name=='explicit-manifest-overlay-style-logo' else {'name':name,'status':'passed'})
            for name in value['required_steps']]

def export_policy(proposal):
    authority=load(proposal)['authority']
    return {'schema_version':1,'rules_revision':authority['rules_revision'],
            'requester_uid':authority['signer_uid'],'producer':authority['producer']}
