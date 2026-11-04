"""Read root-admitted immutable CI configurations, selected only by a digest.

This reader neither admits proposals nor builds policies. The intake principal
and candidate cannot write the registry. Root admission must separately verify
the source observation and build the fixed control recipe before insertion.
"""
import os
from pathlib import Path
import stat
import contract as C

REGISTRY=Path('/var/lib/mrjam-validation-admissions')
FIELDS={'authority','producer','worker','details'}
ANCHOR_FIELDS=('rules_revision','required_steps','not_established','collector_uid',
               'signer_uid','requester_uid','key_id','public_key_der')
RECIPE_FIELDS=('producer_recipe_sha256','worker_core_sha256',
               'collector_recipe_sha256','contract_sha256')


def read_fd(fd,maximum,owner):
    info=os.fstat(fd)
    C.require(stat.S_ISREG(info.st_mode) and info.st_uid==owner
              and stat.S_IMODE(info.st_mode)==0o444 and 0<info.st_size<=maximum,
              'ADMISSION_FILE_METADATA_REFUSED')
    raw=os.read(fd,maximum+1)
    after=os.fstat(fd)
    C.require(len(raw)==info.st_size and
              (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns)==
              (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns),
              'ADMISSION_FILE_CHANGED')
    return raw


def entry(proposal,*,directory=REGISTRY,owner=0):
    C.text(proposal,C.HEX)
    fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        info=os.fstat(fd)
        C.require(info.st_uid==owner and not info.st_mode&0o022,'ADMISSION_DIRECTORY_REFUSED')
        child=os.open(proposal+'.json',os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=fd)
        try:raw=read_fd(child,16384,owner)
        finally:os.close(child)
    finally:os.close(fd)
    value=C.parse(raw,16384)
    C.exact(value,{'schema_version','proposal_sha256','files'})
    C.require(type(value['schema_version']) is int and value['schema_version']==1
              and value['proposal_sha256']==proposal,'ADMISSION_DIGEST_REFUSED')
    C.exact(value['files'],FIELDS)
    for binding in value['files'].values():
        C.exact(binding,{'path','sha256'})
        C.text(binding['path'],C.STORE)
        C.require(binding['path'].endswith('.json'),'ADMISSION_STORE_DOCUMENT_REQUIRED')
        C.text(binding['sha256'],C.HEX)
    return value


def store_bytes(path,maximum=131072):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
    try:return read_fd(fd,maximum,0)
    finally:os.close(fd)


def metadata_bytes(path,maximum=131072,*,directory=REGISTRY/'metadata',owner=0):
    """Root-published document bytes, not a mount of the compiler's Nix closure.

    The path is an immutable document identifier; only its SHA-256 filename is
    opened in the metadata view. resolve() checks each document's content hash.
    """
    C.require(type(path) is str and path.startswith('/nix/store/') and len(path)<=4096,
              'ADMISSION_DOCUMENT_IDENTIFIER_REFUSED')
    directory_fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        info=os.fstat(directory_fd)
        C.require(info.st_uid==owner and not info.st_mode&0o022,'ADMISSION_DIRECTORY_REFUSED')
        name=C.sha(path.encode('utf-8'))+'.data'
        fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=directory_fd)
        try:return read_fd(fd,maximum,owner)
        finally:os.close(fd)
    finally:os.close(directory_fd)


def resolve(record,proposal,anchor,bubblewrap,*,read=store_bytes,now=None,profile='platform'):
    """Cross-bind every immutable configuration before a consumer uses it."""
    # Profile is selected by installed control code, never a registry document
    # or a candidate field. Every profile retains its own full anchor equality.
    C.require(profile in ('platform','vise-v1'),'ADMISSION_PROFILE_REFUSED')
    C.policy(anchor)
    C.require(record['proposal_sha256']==proposal,'ADMISSION_DIGEST_REFUSED')
    raw={}
    documents={}
    for name in sorted(FIELDS):
        binding=record['files'][name]
        raw[name]=read(binding['path'])
        C.require(C.sha(raw[name])==binding['sha256'],'ADMISSION_CONTENT_CHANGED')
        documents[name]=C.parse(raw[name])
    authority=C.policy(documents['authority'])
    C.require(authority['accepted_proposals']==[proposal],'ADMISSION_SCOPE_REFUSED')
    C.active_policy(authority,proposal,now)
    for field in ANCHOR_FIELDS:
        C.require(authority[field]==anchor[field],'ADMISSION_ANCHOR_CHANGED')
    producer=C.producer_binding(documents['producer'])
    C.require(authority['producer']==producer,'ADMISSION_PRODUCER_REFUSED')
    for field in RECIPE_FIELDS:
        C.require(producer[field]==anchor['producer'][field],'ADMISSION_RECIPE_CHANGED')
    worker=documents['worker']
    C.exact(worker,{'schema_version','rules_revision','validator_store','bubblewrap_store','closure_file'})
    C.require(type(worker['schema_version']) is int and worker['schema_version']==1
              and worker['rules_revision']==authority['rules_revision']
              and worker['validator_store']==authority['verifier']
              and worker['bubblewrap_store']==bubblewrap
              and C.sha(raw['worker'])==producer['worker_policy_sha256'],
              'ADMISSION_WORKER_REFUSED')
    closure=worker['closure_file']
    C.require(type(closure) is str and closure.endswith('/store-paths'), 'ADMISSION_CLOSURE_REFUSED')
    C.text(closure.removesuffix('/store-paths'),C.STORE)
    C.require(C.sha(read(closure,262144))==producer['closure_sha256'],'ADMISSION_CLOSURE_REFUSED')
    details=documents['details']
    common={'schema_version','report_policy','report_policy_sha256','verifier',
            'verifier_nar_hash','runtime','runtime_sha256','required_steps'}
    extra=({'overlay_manifest','overlay_manifest_sha256','selected_overlay','selected_entry'}
           if profile=='platform' else {'profile'})
    C.exact(details,common|extra)
    C.require(type(details['schema_version']) is int
              and details['schema_version']==(1 if profile=='platform' else 2),
              'ADMISSION_DETAILS_REFUSED')
    for name in ('verifier','verifier_nar_hash','report_policy_sha256','required_steps'):
        C.require(details[name]==authority[name],'ADMISSION_DETAILS_REFUSED')
    C.text(details['report_policy'],C.STORE)
    report_raw=read(details['report_policy'])
    C.require(C.sha(report_raw)==authority['report_policy_sha256'],'ADMISSION_REPORT_POLICY_REFUSED')
    report_policy=C.parse(report_raw)
    C.require(report_policy['rules_revision']==authority['rules_revision']
              and [{key:source[key] for key in ('id','repository','revision','tree_sha')}
                   for source in report_policy['sources']]==authority['sources'],
              'ADMISSION_SOURCE_BINDING_REFUSED')
    C.text(details['runtime'],C.STORE)
    runtime_raw=read(details['runtime'])
    C.require(C.sha(runtime_raw)==details['runtime_sha256'],'ADMISSION_RUNTIME_REFUSED')
    runtime=C.parse(runtime_raw)
    if profile=='vise-v1':
        import authority_profile as V
        C.require(details['profile']=='vise-v1' and runtime['policy']==details['report_policy'],
                  'ADMISSION_PROFILE_REFUSED')
        V.expected_steps(authority,report_raw,contract=C,rules_revision=anchor['rules_revision'])
        for name in ('vise_dependencies','vise_schema','vise_adopt_role',
                     'vise_adoption_check','vise_schema_contract','vise_runtime_entry'):
            C.text(runtime[name],C.STORE)
        tests=runtime['vise_api_tests']
        C.require(type(tests) is str and tests.endswith('/api-tests.mjs'),'ADMISSION_API_CONTRACT_REFUSED')
        C.text(tests.removesuffix('/api-tests.mjs'),C.STORE)
        return documents
    overlay=details['overlay_manifest']
    C.require(type(overlay) is str and overlay.endswith('/manifest.json'),'ADMISSION_OVERLAY_REFUSED')
    C.text(overlay.removesuffix('/manifest.json'),C.STORE)
    C.require(runtime['policy']==details['report_policy']
              and runtime['manifest_overlays']==overlay.removesuffix('/manifest.json'),
              'ADMISSION_RUNTIME_REFUSED')
    overlay_raw=read(overlay)
    C.require(C.sha(overlay_raw)==details['overlay_manifest_sha256'],'ADMISSION_OVERLAY_REFUSED')
    overlays=C.parse(overlay_raw)
    C.require(details['selected_overlay']=='style-logo'
              and [item for item in overlays['overlays'] if item['case']=='style-logo']==[details['selected_entry']]
              and [(item['id'],item['manifest_overlay']) for item in report_policy['frontends']
                   if item['manifest_overlay'] is not None]==[('style-logo','style-logo')],
              'ADMISSION_OVERLAY_REFUSED')
    return documents
