import hashlib,json,re,subprocess
from pathlib import Path
ROOT=Path.cwd();HERE=ROOT/'operations/ci/current-validator-v1';LOCAL=ROOT/'.local/ci-current-validator-v1-20261103'
def item(path):return {'path':str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
binding=json.loads((HERE/'proposed-bindings-20261103.json').read_bytes())
evaluation=json.loads((LOCAL/'evaluation-002.json').read_bytes());assert evaluation['all_passed'] is True and len(evaluation['results'])==12
authority=(LOCAL/'authority-002.stdout').read_text().strip();assert authority==evaluation['authority_package']
assert re.search(r'Ran 12 tests in .*\n\nOK\n', (LOCAL/'tests-002.stderr').read_text())
policy=json.loads((HERE/'authority-policy.proposed.json').read_bytes())
assert len(policy['required_steps'])==len(set(policy['required_steps']))==75
assert all(re.fullmatch('[a-z][a-z0-9-]{0,100}',x) for x in policy['required_steps'])
previous=json.loads((ROOT/'operations/forgejo/qualification-complete-chain-20261031.json').read_bytes())['result']['integration_evidence']['verification']
renamed=[{'before':x['name'],'after':x['name'].lower()} for x in previous['steps'] if x['name']!=x['name'].lower()];assert len(renamed)==8
assert 'AUTHORITY_INPUT_REFUSED' in (LOCAL/'authority-001.stderr').read_text()
package_info=json.loads(subprocess.check_output(['nix','--extra-experimental-features','nix-command','path-info','--json',binding['validator'],binding['source'],authority]))
source_names=['package.nix','readiness.py','policy_v2.py','overlay.json','policy.json','staging.nix','bindings.nix','authority-policy.proposed.json','prepare_authority_policy.py','evaluation.nix','test_current_validator.py','record_qualification.py','inspect.py']
value={'schema_version':1,'date':'2026-11-03','status':'passed-targeted-qualification','production_access':False,'activation_performed':False,'application_validation_performed':False,'attestation_emitted':False,
 'bindings':binding,'package_info':package_info,'sources':[item(HERE/name) for name in source_names],
 'source_selection_proof':item(HERE/'source-choice-20261103.json'),'current_application_patch_proof':item(ROOT/'operations/runtime/mateval-readiness-v1/qualification-20261102.json'),
 'targeted_tests':{'count':12,'exit':0,'log':item(LOCAL/'tests-002.stderr')},'nix_evaluation':{'assertions':evaluation['results'],'log':item(LOCAL/'evaluation-002.json'),'synthetic_context':evaluation['scope']},
 'actual_authority_policy_package':authority,'authority_package_build_log':item(LOCAL/'authority-002.stderr'),
 'control_changes':['Original policy parser retained byte-identically as base_policy; a closed schema2 wrapper requires the exact reviewed overlay.','Runner adds only the readiness import, fixed pre-Cargo overlay call/step and lowercase Elm entrypoint report label.','All other original executable modules compare byte-identically; runtime changes only its immutable policy path.','Old validator, old runtime and old synthetic policy are absent from the new 133-path closure.'],
 'label_normalization':{'reason':'Actual authority package rejected eight historical uppercase step labels against its frozen lowercase protocol.','mapping':renamed,'commands_and_test_selection_unchanged':True,'first_refused_build':item(LOCAL/'authority-001.stderr'),'final_authority_contract_build_passed':True},
 'history':[{'kind':'Nix evaluation context error before build','log':item(LOCAL/'package-001.stderr'),'correction':'Parse the fixed runtime JSON without string context, then restore that same dependency context before writeText; generated dependency references remain intact.'}],
 'limits':['Twelve targeted tests and twelve Nix assertions do not establish the 75 application checks as passed.','A future local full validation produces new artifacts; no byte equality with wasr/current frontends is claimed yet.','No Forgejo dispatch, production attestation, human review or deployment authority is established.','Workers/adopters/migrations outside the three-artifact protocol retain separate proofs.','Git SHA1 tree identities, selected-content/proposal SHA256 and artifact hashes remain distinct; release-manifest mapping is not established.']}
target=HERE/'qualification-20261103-001.json';target.write_text(json.dumps(value,sort_keys=True,indent=2)+'\n');print(json.dumps(item(target),sort_keys=True))
