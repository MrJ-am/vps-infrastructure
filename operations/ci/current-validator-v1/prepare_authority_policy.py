"""Bind a proposed content policy to observed public key and actual artifacts."""
import base64,datetime,hashlib,json,subprocess
from pathlib import Path
ROOT=Path.cwd();HERE=ROOT/'operations/ci/current-validator-v1';LOCAL=ROOT/'.local/ci-current-validator-v1-20261103'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
package=(LOCAL/'package-003.stdout').read_text().strip()
source=(LOCAL/'staging-001.stdout').read_text().strip()
closure=Path((LOCAL/'closure-002.stdout').read_text().strip())
paths=(closure/'store-paths').read_text().splitlines()
for forbidden in ('/nix/store/p2494a4mh5nsp77sfzrfd8zhinz34bmp-mrjam-validate','/nix/store/0py92lckwf8la1w2pq6d0cgd42xnpywr-mrjam-verifier-runtime.json','/nix/store/4x5fryy0wsxlhsa4bpfdnqh5fxr9mp0a-policy.json'):
    assert forbidden not in paths
info=json.loads(subprocess.check_output(['nix','--extra-experimental-features','nix-command','path-info','--json',package]))
info=info[package] if isinstance(info,dict) else info[0]
key_path=ROOT/'.local/deployment-20261101/ci-key-bootstrap-result-001.json'
key=json.loads(key_path.read_bytes())
assert set(key)=={'schema_version','code','key_id','public_key_der','private_key_exported','ci_activated'}
assert key['code']=='AUTHORITY_KEY_CREATED' and key['private_key_exported'] is False and key['ci_activated'] is False
public=base64.b64decode(key['public_key_der'],validate=True)
assert len(public)==44 and public.startswith(bytes.fromhex('302a300506032b6570032100')) and hashlib.sha256(public).hexdigest()==key['key_id']=='f0e41983bbc2c2ff0bc1ccda81156d2e0b26f146d7dd0ec7497d03e2810fb758'
report_policy=json.loads((HERE/'policy.json').read_bytes())
previous=json.loads((ROOT/'operations/forgejo/qualification-complete-chain-20261031.json').read_bytes())['result']['integration_evidence']['verification']
sources=[{field:item[field] for field in ('id','repository','revision','tree_sha')} for item in report_policy['sources']]
assert sources==previous['sources']
steps=[item['name'].lower() for item in previous['steps']];assert len(steps)==74 and steps[0]=='complete-trees-submodules-and-locked-tools'
steps.insert(1,'rust-reviewed-readiness-overlay')
proposal=json.loads((LOCAL/'proposal-sha256.json').read_bytes())
assert proposal==sha(Path(source)/'manifest.json')
window=datetime.datetime(2026,11,3,0,31,tzinfo=datetime.timezone.utc)
value={'schema_version':1,'scope':'mrjam-validation-content-authority-v1','rules_revision':report_policy['rules_revision'],
 'verifier':package,'verifier_nar_hash':info['narHash'],'closure_sha256':sha(closure/'store-paths'),'report_policy_sha256':sha(HERE/'policy.json'),
 'collector_uid':952,'signer_uid':953,'requester_uid':950,'key_id':key['key_id'],'public_key_der':key['public_key_der'],
 'not_before':int(window.timestamp()),'expires_at':int((window+datetime.timedelta(days=7)).timestamp()),
 'required_steps':steps,'sources':sources,'accepted_proposals':[proposal],'not_established':previous['not_established']}
assert value['not_established']==['production ACL and signing identity','real SSO and production database state','backup restoration',*report_policy['out_of_scope']]
target=HERE/'authority-policy.proposed.json';target.write_text(json.dumps(value,sort_keys=True,indent=2)+'\n')
binding={'schema_version':1,'status':'proposed-not-adopted-or-activated','public_key_observation_sha256':sha(key_path),'validator':package,'source':source,'closure':str(closure),'closure_path_count':len(paths),'proposal_sha256':proposal,'authority_policy_sha256':sha(target),'report_policy_sha256':sha(HERE/'policy.json'),'rules_revision':value['rules_revision'],'policy_window_utc':['2026-11-03T00:31:00Z','2026-11-10T00:31:00Z'],'required_steps_count':len(steps),'application_validation_performed':False,'attestation_emitted':False,'git_tree_algorithm':'Git SHA-1','proposal_and_selected_content_algorithm':'SHA-256; separate bindings, not interchangeable with Git tree identifiers'}
(HERE/'proposed-bindings-20261103.json').write_text(json.dumps(binding,sort_keys=True,indent=2)+'\n')
print(json.dumps(binding,sort_keys=True))
