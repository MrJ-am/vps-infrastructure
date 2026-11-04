"""Record separate consumer proof without rewriting the original failed run."""
import hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent
LOCAL=ROOT/'.local/ci-authority-report-details-v3-20261103'
RUN=ROOT/'.local/ci-current-validator-v1-20261103/native-validation-001'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def entry(path):
    path=Path(path);raw=path.read_bytes()
    return {'path':str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),'bytes':len(raw),'sha256':sha(raw)}
def info(path):
    value=json.loads(subprocess.check_output(['nix','--extra-experimental-features','nix-command','path-info','--json',str(path)],stderr=subprocess.DEVNULL))
    return value[str(path)] if isinstance(value,dict) else value[0]
def main():
    package=Path((LOCAL/'package-002.stdout').read_text().strip())
    assert str(package)=='/nix/store/cqz4jlhpis05gj4wcjgaddb45qbfwpz0-mrjam-validation-authority-report-details-3'
    evaluation=json.loads((LOCAL/'evaluation-002.json').read_bytes());assert evaluation['all_passed'] and len(evaluation['results'])==10
    tests=(LOCAL/'tests-001.stderr').read_text();assert 'Ran 12 tests' in tests and tests.rstrip().endswith('OK')
    observed=json.loads((RUN/'application-observation-001.json').read_bytes());assert observed['application_checks_passed']==75 and observed['raw_report_consumer_code']=='REQUIRED_STEPS_REFUSED'
    original=(RUN/'result.json').read_bytes();assert sha(original)=='8dd98924157d1a42c2b727b97eb0f291131f9a16a1a8b245d0743cad16135585' and json.loads(original)['status']=='failed'
    for a in observed['artifacts']:
        e=entry(RUN/'artifacts'/a['name']);assert e['sha256']==a['sha256'] and e['bytes']==a['bytes']
    assert observed['artifacts'][2]['sha256']=='92d4468cbab1dd20f38fee9d16390c7ab0ed4a8c28dbc16aea3e4a8e6fee760d'
    comparison=json.loads((RUN/'comparison-001.json').read_bytes())
    assert all(x['payload_files_byte_identical'] and x['artifact_metadata_fields_changed']==['input_manifest_sha256'] for x in comparison['frontends'].values())
    assert comparison['server']['byte_identical'] is False
    sources=['CHOIX.org','README.org','descriptor.json','report_details.py','package.nix','module.nix','build.nix','evaluation.nix','test_report_details.py','compare_artifacts.py','record_qualification.py']
    logs=['package-001.stdout','package-001.stderr','package-002.stdout','package-002.stderr','tests-001.stdout','tests-001.stderr','evaluation-001.json','evaluation-001.stderr','evaluation-002.json','evaluation-002.stderr','comparison-001.stdout','comparison-001.stderr']
    value={'schema_version':1,'status':'passed-with-explicit-separate-scopes','scope':'exact-consumption-of-existing-public-report-not-a-new-application-run',
      'package':{'store_path':str(package),'nar_hash':info(package)['narHash'],'files':[entry(p) for p in sorted((package/'lib').glob('*.py'))]},
      'sources':[entry(HERE/name) for name in sources],'logs':[entry(LOCAL/name) for name in logs],
      'native_tests':{'passed':12,'signature_key':'invented ephemeral Ed25519 only','collector_receipt':'synthetic receipt over existing measured artifacts','application_tests_reexecuted':False},
      'nix_evaluation':evaluation,'original_validation':{'result':json.loads(original),'result_binding':entry(RUN/'result.json'),'observation':entry(RUN/'application-observation-001.json'),'raw_report':entry(RUN/'artifacts/verification.json'),'artifacts':observed['artifacts'],'application_steps_passed':75,'report_rewritten':False},
      'byte_comparison':comparison,'comparison_binding':entry(RUN/'comparison-001.json'),
      'separate_prior_proofs':[entry(ROOT/'operations/ci/integration-v1/review-20261103-001.json'),entry(ROOT/'operations/ci/current-validator-v1/review-20261103-001.json'),entry(ROOT/'operations/ci/current-validator-v1/review-local-launch-20261103-001.json')],
      'production_access':False,'production_key_read':False,'production_attestation_emitted':False,'forgejo_dispatch_performed':False,'deployment_authorized':False,
      'limits':['No rerun of the 75 application steps; original global failed result and full report remain unchanged.','Synthetic signature/receipt proves the consumer and unchanged client, not production collection or signing.','No new systemd VM; same unit restrictions evaluated and prior credentials/UID proof separately referenced.','Seven frontend payloads match the live baseline; new server ELF is not byte-identical.','Rules b02 are proposed, not observed as adopted by this proof.','Workers, adopters, release-manifest linkage, human review and deployment authorization are not established.','Cached validation may be reused; issued_at is signature time, not a claim of fresh execution for every job.']}
    (HERE/'qualification-20261103-001.json').write_text(json.dumps(value,sort_keys=True,indent=2)+'\n')
    application={'schema_version':1,'scope':'one-local-application-run-followed-by-separate-consumer-proof','original_global_result':json.loads(original),'original_result_binding':entry(RUN/'result.json'),
      'validator':observed['verifier'],'verifier_nar_hash':observed['verifier_nar_hash'],'report_policy_sha256':observed['report_policy_sha256'],'proposal_sha256':comparison['proposal_sha256'],
      'rules_revision':'b02bdf1b5d63dcf0e0610723788a7ca7e384932c','rules_adoption_established':False,'application_steps_passed':75,'raw_report':entry(RUN/'artifacts/verification.json'),'artifacts':observed['artifacts'],
      'observation':entry(RUN/'application-observation-001.json'),'comparison':comparison,'consumer_qualification':entry(HERE/'qualification-20261103-001.json'),
      'launcher':entry(ROOT/'operations/ci/current-validator-v1/run_local_validation.py'),'launcher_review':entry(ROOT/'operations/ci/current-validator-v1/review-local-launch-20261103-001.json'),
      'limits':{'memory_bytes':2147483648,'cpu_percent':100,'tasks':256,'worker_timeout_seconds':1800},
      'substitutions':['Local UID owns fixed read-only staging copy; worker.verify_input uses this UID and fixed local input root.','Single-UID user namespace precedes unchanged worker sandbox so process limit is isolated from the desktop.','Outer subprocess stderr is retained locally; inner application outputs remain silenced.','No real collector receipt, Forgejo dispatch, signing key or production attestation.'],
      'application_validation_repeated':False,'raw_report_rewritten':False,'production_access':False,'production_attestation_emitted':False,'production_key_read':False,'release_manifest_binding_established':False,'workers_or_adopters_covered':False}
    target=ROOT/'operations/ci/current-validator-v1/local-application-run-20261103-001.json';target.write_text(json.dumps(application,sort_keys=True,indent=2)+'\n')
    print(json.dumps({'qualification':entry(HERE/'qualification-20261103-001.json'),'application_observation':entry(target)},sort_keys=True))
if __name__=='__main__':main()
