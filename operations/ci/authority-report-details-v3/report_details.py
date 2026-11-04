"""Exact, immutable detailed report entry; no candidate-selected exceptions."""
import os,stat
import contract as C

DESCRIPTOR_PATH='@report-details@'

def descriptor():
    fd=os.open(DESCRIPTOR_PATH,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
    with os.fdopen(fd,'rb') as stream:
        meta=os.fstat(stream.fileno())
        C.require(stat.S_ISREG(meta.st_mode) and meta.st_uid==0 and not meta.st_mode&0o222 and 0<meta.st_size<=65536,'REPORT_DETAILS_METADATA_REFUSED')
        value=C.parse(stream.read(65537),65536)
    C.exact(value,{'schema_version','report_policy','report_policy_sha256','verifier','verifier_nar_hash','runtime','runtime_sha256','overlay_manifest','overlay_manifest_sha256','selected_overlay','selected_entry','required_steps'})
    C.require(type(value['schema_version']) is int and value['schema_version']==1 and value['selected_overlay']=='style-logo','REPORT_DETAILS_BINDING_REFUSED')
    return value

def expected_steps(policy):
    details=descriptor()
    for name in ('report_policy_sha256','verifier','verifier_nar_hash','required_steps'):
        C.require(policy[name]==details[name],'REPORT_DETAILS_BINDING_REFUSED')
    entry=details['selected_entry']
    C.require(entry['case']=='style-logo','REPORT_DETAILS_BINDING_REFUSED')
    target='explicit-manifest-overlay-style-logo'
    C.require(policy['required_steps'].count(target)==1,'REPORT_DETAILS_BINDING_REFUSED')
    return [({'name':name,'status':'passed','base_sha256':entry['base_sha256'],'corrected_sha256':entry['corrected_sha256']} if name==target else {'name':name,'status':'passed'}) for name in policy['required_steps']]
