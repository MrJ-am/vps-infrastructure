"""Record observed local content; never turn a build into production authority."""
from pathlib import Path
import hashlib,json,subprocess
ROOT=Path(__file__).resolve().parents[3];LOCAL=ROOT/'.local/ci-artifact-recovery-20261102'
PATHS={
 'runner':'/nix/store/cdj7b2dnn83kbwwhrpia79zbfllxbzsb-mrjam-forgejo-runner-13.2.0',
 'stager':'/nix/store/bfzw076149c1bca4xnr4q48saaw1wby7-mrjam-validation-stage-sources-1',
 'source_bundle':'/nix/store/zjwbgmna6pyw7p151pzrgm20wi2jzfqv-mrjam-public-source-bundle-for-staging',
 'validator_corrected':'/nix/store/p2494a4mh5nsp77sfzrfd8zhinz34bmp-mrjam-validate'}
OLD='/nix/store/wwnqd5sjcixkjmfwwbb3b5b3ggc2bj8l-mrjam-validate'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def info(p):
 x=json.loads(subprocess.check_output(['nix','--extra-experimental-features','nix-command','path-info','--json',p],stderr=subprocess.DEVNULL))[p]
 return {k:x[k] for k in ['deriver','narHash','narSize','references']}
def main():
 verify=['nix','--extra-experimental-features','nix-command','store','verify','--no-trust','--recursive',*PATHS.values()]
 verified=subprocess.run(verify,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=180,check=True)
 (LOCAL/'recursive-verify.stdout').write_bytes(verified.stdout);(LOCAL/'recursive-verify.stderr').write_bytes(verified.stderr)
 a=ROOT/'operations/forgejo/qualification-complete-chain-20261031.json';b=ROOT/'operations/forgejo/qualification-staging-20261031.json'
 x=json.loads(a.read_bytes());y=json.loads(b.read_bytes());entries={}
 for name,path in PATHS.items():
  observed=info(path);historical=x['nix']['path_info'].get(path,y['path_info'].get(path))
  if historical is not None:assert observed=={k:historical[k] for k in observed}
  entries[name]={'path':path,'path_info':observed,'historical_output_exact':historical is not None}
 assert not Path(OLD).exists()
 result=json.loads((LOCAL/'validator-targeted-result.json').read_bytes());assert result['all_passed'] is True and len(result['checks'])==8
 manifests=[]
 for path in sorted((ROOT/'.local/exports-20261101-lfs-b829cbdc').rglob('review-manifest.json')):
  data=json.loads(path.read_bytes());paths=list(data['closure']);assert len(paths)==data['closure_paths'];assert not set([OLD,*PATHS.values()])&set(paths)
  manifests.append({'file':str(path.relative_to(ROOT)),'sha256':sha(path),'closure_paths_count':len(paths),'ci_targets_absent':True})
 assert len(manifests)==2
 sources={str(p.relative_to(ROOT)):sha(p) for p in sorted((ROOT/'operations/forgejo/recovery').iterdir()) if p.is_file()}
 logs={n:sha(LOCAL/n) for n in ['runner-staging-build.log','staging-source-build.log','validator-build.log','validator-build-002.log','validator-corrected-build.log','recursive-verify.stderr']}
 value={'schema_version':1,'authority':'local-content-recovery-and-targeted-tests','production_access':False,'production_ready':False,'activation_performed':False,'artifacts':entries,'historical_validator':{'path':OLD,'output_available':False,'derivation_reproduced':'/nix/store/zds5r7q12q7f3np19cy6p2zm04fwxxhq-mrjam-validate.drv','reason':'upstream installer requires /usr/bin/env absent from strict sandbox; per-build path request rejected for untrusted user; parent reported sudo password required, no privileged action taken','recipe_diff':'only existing postPatch patchShebangs ./install.sh; archive and version lock unchanged'},'targeted_qualification':result,'recovered_inputs':{'accepted_rules_revision':'eb71ffe5944943474c5ee483e66c270b5976ab90','historical_synthetic_rules_revision':'93bd67666a3b4be9657c333931fa25b2359e165b','governance_refs_modified':False,'old_private_data_read':False,'proposal_files':815,'proposal_manifest_sha256':sha(LOCAL/'proposal-fixture/manifest.json'),'policy_sha256':sha(LOCAL/'policy.json'),'runtime_materialization_sha256':sha(LOCAL/'runtime-inputs/materialization.json'),'runtime_source_files':463,'cargo_packages':225,'elm_cache_files':449,'frontend_resources':92,'elm_docs_regenerated_exact':['elm/http/2.0.0/docs.json','elm/time/1.0.0/docs.json']},'original_export_manifests':manifests,'recursive_content_verification':{'performed':True,'exit_code':0,'command':['nix','--extra-experimental-features','nix-command','store','verify','--no-trust','--recursive',*PATHS.values()]},'historical_receipts_sha256':{str(p.relative_to(ROOT)):sha(p) for p in [a,b]},'recovery_sources_sha256':sources,'local_logs_sha256':logs,'limits':['The first three roots exactly match historical NAR hashes, sizes, derivations and references.','The corrected validator is a new root; its eight checks do not rerun the full application pipeline or Forgejo/systemd integration.','All current policies and the source bundle are historical synthetic qualification bindings, not adopted production CI policy.','No validation signing authority, human approval, delivery executor or live CI dispatch is established by this inventory.']}
 out=ROOT/'operations/forgejo/qualification-artifact-recovery-20261102.json';out.write_text(json.dumps(value,sort_keys=True,indent=2)+'\n');print(json.dumps({'receipt':str(out.relative_to(ROOT)),'sha256':sha(out),'historical_exact_roots':3,'corrected_validator_checks':8}))
if __name__=='__main__':main()
