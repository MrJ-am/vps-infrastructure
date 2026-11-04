"""Keep the original source/tree rules; require the sole reviewed overlay."""
import base_policy as original
from base_policy import *
import readiness

def checked_policy(value):
    original.exact(value,('schema_version','status','rules_revision','sources','frontends','out_of_scope','rust_manifests','readiness_overlay'))
    original.require(type(value['schema_version']) is int and value['schema_version']==2,'POLICY_VERSION')
    readiness.checked(value['readiness_overlay'])
    baseline={key:content for key,content in value.items() if key!='readiness_overlay'}
    baseline['schema_version']=1
    original.checked_policy(baseline)
    original.require(next(item['revision'] for item in value['sources'] if item['id']=='platform')==readiness.CONTRACT['base_platform_revision'],'READINESS_BASE_REVISION_REFUSED')
    return value
