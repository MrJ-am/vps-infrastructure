"""Local content check of the completed proposal003 run; never a signing policy."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
PROPOSAL='04754e2c5e531c37bd06864ed2becb3fc218d20d780d9a8c8e1b045956a5d04d'
POLICY_SHA='be4a54ba570c87dcc53f4522e77c748e14b9fe1aa5fb9995a7600a949510a8e9'
DESCRIPTOR=Path('/nix/store/fdxh1p60i5bdspiqjid5wjv52k9r4scr-mrjam-authority-report-details-v3.json')
PREVIOUS_POLICY=Path('/nix/store/d8bhnl18vsch1zbrvm28w6dvn6acz1k6-mrjam-validation-authority-policy.json')

def require(value,code):
    if not value:raise ValueError(code)

def expected(artifacts):
    raw=(HERE/'aligned-policy.json').read_bytes()
    require(hashlib.sha256(raw).hexdigest()==POLICY_SHA,'EXPECTED_POLICY_CHANGED')
    policy=json.loads(raw)
    details=json.loads(DESCRIPTOR.read_bytes())
    previous=json.loads(PREVIOUS_POLICY.read_bytes())
    require(details['required_steps']==previous['required_steps'],'PROTECTED_STEPS_CHANGED')
    require(details['required_steps'].count('rust-reviewed-readiness-overlay')==1,'OVERLAY_STEP_CHANGED')
    # The readiness correction now belongs to the platform Git tree. Only its
    # old overlay application step is removed; every test remains required.
    names=[s for s in details['required_steps'] if s!='rust-reviewed-readiness-overlay']
    steps=[{'name':name,'status':'passed'} for name in names]
    entry=details['selected_entry']
    require(entry['case']=='style-logo','DETAILS_CASE_CHANGED')
    for step in steps:
        if step['name']=='explicit-manifest-overlay-style-logo':
            step.update({key:entry[key] for key in ('base_sha256','corrected_sha256')})
    return {'schema_version':1,'decision':'passed','authority':'local-verifier-content-receipt',
            'independent_adoption_established':False,'production_authorized':False,
            'proposal_sha256':PROPOSAL,'rules_revision':policy['rules_revision'],
            'policy_sha256':POLICY_SHA,'steps':steps,
            'sources':[{key:item[key] for key in ('id','repository','revision','tree_sha')} for item in policy['sources']],
            'artifacts':artifacts,'not_established':previous['not_established']}

def check(report,artifacts):
    require(type(report) is dict and type(report.get('schema_version')) is int
            and report.get('independent_adoption_established') is False
            and report.get('production_authorized') is False,'REPORT_SCHEMA_REFUSED')
    require(report==expected(artifacts),'EXACT_REPORT_CONTENT_REFUSED')

def main():
    directory=HERE.parents[2]/'.local/deployment-20261101/aligned-native-validation-002/artifacts'
    metadata=[]
    for name,maximum in [('server',64*1024**2),('frontend.tar',64*1024**2),('verification.json',65536)]:
        path=directory/name
        require(path.is_file() and not path.is_symlink() and 0<path.stat().st_size<=maximum,'ARTIFACT_METADATA_REFUSED')
        raw=path.read_bytes()
        metadata.append({'name':name,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
    report=json.loads((directory/'verification.json').read_bytes())
    check(report,metadata[:2])
    result={'schema_version':1,'status':'passed','required_steps_passed':len(report['steps']),
            'artifacts':metadata,'proposal_sha256':PROPOSAL,'policy_sha256':POLICY_SHA,
            'application_validation_repeated':False,'original_run_elapsed_seconds':1086.095,
            'original_harness_final_check':'old-reader-refused-detailed-style-overlay-entry',
            'production_attestation_emitted':False,'production_access':False,
            'private_key_accessed':False,'report_matches_local_expected_content_only':True,
            'limits':['Normal cargo test retains its explicitly ignored memory measurement.',
                      'No production policy adopted and no deployment authorized by this check.']}
    (HERE/'qualification-aligned-validation-003.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps(result,sort_keys=True))

if __name__=='__main__':main()
