"""Record observed VM groups without relabelling the failed auxiliary run."""
import hashlib,json,re,subprocess
from pathlib import Path
ROOT=Path.cwd()
LOCAL=ROOT/'.local/ci-integration-v1-20261103'
PACKAGE=Path('/nix/store/d48pqnf7q0hfqkhvbg6vd0nk6ffihzy5-mrjam-validation-authority-credentials-2')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def item(path):return {'path':str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),'bytes':path.stat().st_size,'sha256':sha(path)}
def write(path,value):path.write_text(json.dumps(value,sort_keys=True,indent=2)+'\n')
log=LOCAL/'build-008.stderr';text=log.read_text()
groups=['prepare','inactive-boundaries','fresh-chain','cache-reuse','wrong-peers','key-separation','legacy-cache-refused','tamper-refused','wrong-key-refused','expiry-refused']
for group in groups:
    assert re.search(r'\(finished: subtest: '+re.escape(group)+r', in [0-9.]+ seconds\)',text)
assert 'SYNTHETIC_VIEW_UNAVAILABLE' in text and 'Test "credential-reader-boundaries" failed' in text
fixture=Path('/nix/store/ypdb73ispcqgg3jnkrps94g0m0bc3i6j-mrjam-ci-synthetic-unit-fixture/fixture.py')
binding_path=Path(re.search(r"Path\('([^']+)'\)",fixture.read_text()).group(1))
binding=json.loads(binding_path.read_bytes());assert binding['authority']==str(PACKAGE)
output=Path((LOCAL/'reader-boundaries-001.stdout').read_text().strip())
result=json.loads((output/'result.json').read_bytes())
assert len(result['checks'])==9 and [x['accepted'] for x in result['checks']]==[True,False,False,False,False,False,False,False,True]
assert 'test script finished' in (LOCAL/'reader-boundaries-001.stderr').read_text()
refs=subprocess.check_output(['nix-store','--query','--references',str(PACKAGE)],text=True).splitlines()
authority_policy=next(x for x in refs if x.endswith('-mrjam-validation-authority-policy.json'))
export_policy=next(x for x in refs if x.endswith('-mrjam-validation-export-policy.json'))
openssl=next(x for x in refs if '-openssl-' in x)+'/bin/openssl'
v1=ROOT/'operations/ci/authority-v1';v2=ROOT/'operations/ci/authority-credentials-v2'
compared={}
for name in ('contract','producer','collector','exporter','client','signer'):
    source=(v1/(name+'.py')).read_text()
    for before,after in {'@authority-policy@':authority_policy,'@export-policy@':export_policy,'@openssl@':openssl}.items():source=source.replace(before,after)
    if name=='signer':
        for before,after in {'import collector as S':'import collector as S\nimport signing_credential as K','key=C.regular_file(private_key_path,owner=os.getuid(),mode=0o400,maximum=4096)':'key=K.read_key(private_key_path)'}.items():
            assert source.count(before)==1;source=source.replace(before,after)
    actual=PACKAGE/'lib'/(name+'.py');assert actual.read_text()==source
    compared[name]={'packaged_sha256':sha(actual),'source_sha256':sha(v1/(name+'.py'))}
assert (PACKAGE/'lib/signing_credential.py').read_bytes()==(v2/'reader.py').read_bytes()
assert (PACKAGE/'lib/frozen_worker.py').read_bytes()==(ROOT/'operations/forgejo/worker.py').read_bytes()
package_info=json.loads(subprocess.check_output(['nix','--extra-experimental-features','nix-command','path-info','--json',str(PACKAGE)]))
sources=[]
for directory in ('authority-v1','authority-credentials-v2','coordinator-v1','integration-v1'):
    for path in sorted((ROOT/'operations/ci'/directory).glob('*')):
        if path.is_file() and path.suffix in ('.py','.nix','.go'):
            sources.append(item(path))
sources.append(item(ROOT/'operations/ci/integration-v1/public-fixture-policy.json'))
receipt={
 'schema_version':1,'date':'2026-11-03','status':'passed-in-declared-scopes','production_access':False,
 'package':str(PACKAGE),'package_info':package_info,'packaged_source_checks':compared,
 'credential_reader_source':item(v2/'reader.py'),'worker_core_byte_identical':True,
 'integrated_scope':{'checks_passed':groups,'count':10,'original_full_build_exit':1,'auxiliary_failure':'SYNTHETIC_VIEW_UNAVAILABLE in an invented credential view belonging to another systemd unit; not a signing-chain failure','failed_build_not_relabelled':True,'log':item(log),'derivation':'/nix/store/xlxdx2bjddj9v5qxgg9i82ks9fm8h8y9-vm-test-run-mrjam-ci-distinct-identities-authority-and-coordinator.drv','fixture':item(fixture),'bindings':item(binding_path),'identities':{'collector':61001,'signer':61002,'coordinator':61003,'registrar':61004,'worker':61005,'outsider':61006},'private_coordinator_root':binding['expected_root'],'production_coordinator_root_for_same_policy':binding['real_root']},
 'credential_boundaries':{'build_exit':0,'output':str(output),'result':result,'result_file':item(output/'result.json'),'log':item(LOCAL/'reader-boundaries-001.stderr')},
 'sources':sources,
 'substitutions':['Invented immutable validator, sources, report and signing key; no application build.','An admitted task is supplied through a Go test entrypoint calling the exact bounded coordinator methods, rather than through Forgejo API/daemon.','The test entrypoint closure is added to the otherwise unchanged private coordinator root; the actual service restrictions and distinct UIDs apply.','Negative credential cases use private kernel mount namespaces and then drop root to the exact signer UID; the positive signing chain uses real systemd LoadCredential.'],
 'not_established':['Actual Forgejo job transport or production key/policy.','New validator execution on every job: a bound v2 cache may be reused; issued_at dates signing only.','Human review, merge or deployment authority.'],
 'prior_receipts':[item(ROOT/'operations/ci/authority-v1/qualification-local-20261103-001.json'),item(ROOT/'operations/ci/coordinator-v1/qualification-local-20261103-001.json'),item(ROOT/'operations/ci/integration-v1/diagnosis-credential-20261103.json')],
}
write(ROOT/'operations/ci/integration-v1/qualification-20261103-001.json',receipt)
write(v2/'qualification-20261103-001.json',{'schema_version':1,'date':'2026-11-03','package':str(PACKAGE),'package_info':package_info,'sources':[item(v2/name) for name in ('reader.py','package.nix','module.nix')],'changes':['Fixed exact systemd signing credential reader','Signer import and single key-read call only; all other packaged executable sources compare exactly after existing immutable path substitutions'],'integrated_qualification':item(ROOT/'operations/ci/integration-v1/qualification-20261103-001.json'),'production_access':False,'activation_performed':False})
print(json.dumps({'integrated':item(ROOT/'operations/ci/integration-v1/qualification-20261103-001.json'),'credentials_v2':item(v2/'qualification-20261103-001.json')},sort_keys=True))
