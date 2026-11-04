"""Prepare a data-only packaging binding after fresh independent verification.

The fixed controller supplies job root, off-traffic runtime and verification
adapter under the adoption lock. This module neither merges nor activates.
A missing recipe is rejected before irreversible acceptance.
"""
import json,re
from pathlib import Path
import contract as C,admission_control as A,admission_orchestrator as O
import stage_sources as S
import delivery_profiles as Profiles

STORE=re.compile(r'/nix/store/[0-9abcdfghijklmnpqrsvwxyz]{32}-[A-Za-z0-9+._-]+\Z')
SUPPORTED={'apprendre-a-demontrer','style-mrjam','vision','matheval','mrjam-plateforme'}
TOOLCHAINS='27c05033dd0a7347ccdba0afb4caed5bb359eaeeeb1dd1fedb92ef8dc5701eae'

def store(value):
    C.require(type(value) is str and STORE.fullmatch(value),'CONSTRUCTION_STORE_PATH_REFUSED')
    return Path(value)

def source(path,digest,rules):
    owner=path.lstat().st_uid
    raw=S.source_bytes(path/'manifest.json',S.MAX_MANIFEST,owner)
    manifest,names,directories=S.manifest(raw,digest,rules)
    S.source_tree(path,names,directories,owner)
    for entry in manifest['files']:
        data=S.source_bytes(path/entry['path'],S.MAX_BYTES,owner)
        C.require(len(data)==entry['bytes'] and C.sha(data)==entry['sha256'],'CONSTRUCTION_SOURCE_BYTES_REFUSED')

def binding(root,job,slot,runtime,verify):
    C.require(job['phase']=='validated' and job.get('promotion') is None,'CONSTRUCTION_JOB_NOT_AVAILABLE')
    C.require(slot in {'blue','green'},'CONSTRUCTION_SLOT_REFUSED');store(runtime)
    C.require(job['capture']['proposal']['repository'] in SUPPORTED,'CONSTRUCTION_RECIPE_NOT_AVAILABLE')
    content,rows=verified_content(root,job,verify,profile='platform')
    return dict(content,slot=slot,toolchains_sha256=TOOLCHAINS,runtime=runtime)

def vise_binding(root,job,verify):
    C.require(job['phase']=='validated' and job.get('promotion') is None,'CONSTRUCTION_JOB_NOT_AVAILABLE')
    C.require(Profiles.selected(job['capture']['proposal'])=='vise','CONSTRUCTION_RECIPE_NOT_AVAILABLE')
    content,rows=verified_content(root,job,verify,profile='vise-v1')
    return dict(content,schema_version=2,profile='vise-v1',
        verification_sha256=rows['verification.json']['sha256'])

def verified_content(root,job,verify,*,profile):
    O.W.private_directory(root)
    C.require(root.name==job['id'] and O.read(root/'state.json')==job,'CONSTRUCTION_JOB_CHANGED')
    proposal,policy,envelope,run,expected=verify(root,job)
    digest=job['capture']['proposal_sha256']
    C.require(proposal==job['capture']['proposal'] and envelope['payload']['proposal_sha256']==digest,
        'CONSTRUCTION_AUTHORITY_BINDING_REFUSED')
    admitted=A.load(digest)
    C.require(admitted['authority']==policy,'CONSTRUCTION_AUTHORITY_CHANGED')
    C.require(admitted['details'].get('profile','platform')==profile,'CONSTRUCTION_PROFILE_CHANGED')
    descriptor=C.parse((store(job['bundle'])/'descriptor.json').read_bytes())
    C.require(descriptor['proposal_sha256']==digest
        and descriptor['capture_sha256']==C.sha(O.W.read_file(root/'capture/capture.json',65536)),
        'CONSTRUCTION_CAPTURE_BINDING_REFUSED')
    prepared=store(descriptor['source']);source(prepared,digest,policy['rules_revision'])
    report=store(admitted['details']['report_policy'])
    C.require(C.sha(report.read_bytes())==policy['report_policy_sha256'],'CONSTRUCTION_POLICY_CHANGED')
    artifacts=envelope['payload']['artifacts'];rows={item['name']:item for item in artifacts}
    C.require(len(rows)==len(artifacts) and set(rows)=={'server','frontend.tar','verification.json'},
        'CONSTRUCTION_ARTIFACT_SET_REFUSED')
    for item in artifacts:
        raw=C.regular_file(root/'artifacts'/item['name'],owner=0,mode=0o400,maximum=dict(C.ARTIFACTS)[item['name']])
        C.require(len(raw)==item['bytes'] and C.sha(raw)==item['sha256'],'CONSTRUCTION_ARTIFACT_CHANGED')
    return {'schema_version':1,'proposal_sha256':digest,'artifact_root':str(root/'artifacts'),
        'source':str(prepared),'report_policy':str(report),'report_policy_sha256':policy['report_policy_sha256'],
        'server_sha256':rows['server']['sha256'],'server_bytes':rows['server']['bytes'],
        'frontend_sha256':rows['frontend.tar']['sha256']},rows
