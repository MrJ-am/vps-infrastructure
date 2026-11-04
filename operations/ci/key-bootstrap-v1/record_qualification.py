import hashlib,json,subprocess
from pathlib import Path
ROOT=Path.cwd();HERE=ROOT/'operations/ci/key-bootstrap-v1';LOCAL=ROOT/'.local/ci-key-bootstrap-v1-20261103'
def item(path):return {'path':str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
output=Path((LOCAL/'build-002.stdout').read_text().strip());result=json.loads((output/'result.json').read_bytes())
assert len(result['checks'])==10 and result['production_access'] is False and result['private_key_exported'] is False
package=Path(result['package']);actual=(package/'lib/bootstrap.py').read_text()
refs=subprocess.check_output(['nix-store','--query','--references',str(package)],text=True).splitlines()
openssl=next(x for x in refs if '-openssl-' in x)+'/bin/openssl'
assert actual==(HERE/'bootstrap.py').read_text().replace('@openssl@',openssl)
assert 'test script finished in 97.70s' in (LOCAL/'build-002.stderr').read_text()
info=json.loads(subprocess.check_output(['nix','--extra-experimental-features','nix-command','path-info','--json',str(package)]))
value={'schema_version':1,'date':'2026-11-03','status':'passed','scope':'fixed-root-key-bootstrap-local-invented-VM','package':str(package),'package_info':info,'packaged_source':item(package/'lib/bootstrap.py'),'source_byte_identical_after_openssl_substitution':True,'sources':[item(HERE/name) for name in ('bootstrap.py','package.nix','fixture.py','systemd.nix','record_qualification.py')],'vm_output':str(output),'vm_result':result,'vm_result_file':item(output/'result.json'),'log':item(LOCAL/'build-002.stderr'),'build_exit':0,'duration_seconds':97.70,'first_attempt':{'exit':1,'log':item(LOCAL/'build-001.stderr'),'reason':'fixture included atime in full stat equality; corrected only fixture to preserve all identity/content metadata checks and public-key equality'},'production_access':False,'activation_performed':False,'private_key_exported':False,'fixed_private_path':'/var/lib/mrjam-validation-authority/signing-key','limits':['Only invented keys were generated inside a disposable VM.','No power-loss durability claim beyond explicit file/directory fsync and atomic no-replace rename.','The helper creates or observes the key only; it grants no validation, review, merge or deployment authority.']}
target=HERE/'qualification-20261103-001.json';target.write_text(json.dumps(value,sort_keys=True,indent=2)+'\n');print(json.dumps(item(target),sort_keys=True))
