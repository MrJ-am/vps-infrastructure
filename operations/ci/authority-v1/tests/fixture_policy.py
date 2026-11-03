"""Create public, reproducible synthetic policy; no human or production identity."""
from pathlib import Path
import base64,hashlib,json,subprocess
ROOT=Path(__file__).resolve().parents[4]
DIRECTORY=ROOT/'operations/ci/authority-v1'
OPENSSL='/nix/store/fya253x5ky7rhfz6rkgdwjr1fzf7fy71-openssl-3.6.5-bin/bin/openssl'

def fixture():
    # Public test seed. It must never be used as an operational signing key.
    seed=hashlib.sha256(b'MRJAM AUTHORITY V1 PUBLIC SYNTHETIC TEST KEY ONLY').digest()
    private=bytes.fromhex('302e020100300506032b657004220420')+seed
    public=subprocess.check_output([OPENSSL,'pkey','-inform','DER','-pubout','-outform','DER'],input=private,stderr=subprocess.DEVNULL)
    sha=lambda b:hashlib.sha256(b).hexdigest()
    policy={'schema_version':1,'scope':'mrjam-validation-content-authority-v1','rules_revision':'b'*40,'verifier':'/nix/store/'+'0'*32+'-synthetic-verifier','verifier_nar_hash':'sha256-'+base64.b64encode(b'v'*32).decode(),'closure_sha256':'c'*64,'report_policy_sha256':'d'*64,'collector_uid':61001,'signer_uid':61002,'requester_uid':61003,'key_id':sha(public),'public_key_der':base64.b64encode(public).decode(),'not_before':1793577600,'expires_at':1796169600,'required_steps':['synthetic-code-contract'],'sources':[{'id':'synthetic','repository':'invented/code','revision':'e'*40,'tree_sha':'f'*40}],'accepted_proposals':['a'*64],'not_established':['production activation','human review']}
    binding={'schema_version':1,**{k:policy[k] for k in ['rules_revision','verifier','verifier_nar_hash','closure_sha256','report_policy_sha256']},'worker_policy_sha256':'1'*64,'producer_recipe_sha256':sha((DIRECTORY/'producer.py').read_bytes()),'worker_core_sha256':sha((ROOT/'operations/forgejo/worker.py').read_bytes()),'collector_recipe_sha256':sha((DIRECTORY/'collector.py').read_bytes()),'contract_sha256':sha((DIRECTORY/'contract.py').read_bytes())}
    return {**policy,'producer':binding}

if __name__=='__main__':
    path=ROOT/'.local/ci-authority-v1-20261102';path.mkdir(exist_ok=True)
    policy=fixture()
    (path/'synthetic-policy.json').write_text(json.dumps(policy,sort_keys=True,indent=2)+'\n')
    (path/'synthetic-binding.json').write_text(json.dumps(policy['producer'],sort_keys=True,indent=2)+'\n')
    print(json.dumps({'synthetic':True,'public_test_key_only':True,'policy':str((path/'synthetic-policy.json').relative_to(ROOT))}))
