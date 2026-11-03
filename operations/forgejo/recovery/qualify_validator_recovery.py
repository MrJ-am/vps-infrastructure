"""Targeted local qualification; no CI dispatch, VPS or production authority."""
from pathlib import Path
import base64, hashlib, json, os, shutil, stat, subprocess, tempfile, time
ROOT=Path(__file__).resolve().parents[3]
LOCAL=ROOT/'.local/ci-artifact-recovery-20261102'
OLD='/nix/store/wwnqd5sjcixkjmfwwbb3b5b3ggc2bj8l-mrjam-validate'
NEW='/nix/store/p2494a4mh5nsp77sfzrfd8zhinz34bmp-mrjam-validate'
OLD_RUNTIME='/nix/store/jrrpgnp20h73s728qqw4p256qx45v5z4-mrjam-verifier-runtime.json'
NEW_RUNTIME='/nix/store/0py92lckwf8la1w2pq6d0cgd42xnpywr-mrjam-verifier-runtime.json'
OLD_RUST='/nix/store/484kx0fvz6xl3wfa07m2n692223y1qwa-mrjam-rust-toolchain-1.99.1'
NEW_RUST='/nix/store/2va2x1g4ncjhaih1dk0zxvi97s832pw9-mrjam-rust-toolchain-1.99.1'

def run(args,**kwargs):
 return subprocess.run(args,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120,**kwargs).stdout

def digest(b):return hashlib.sha256(b).hexdigest()

def main():
 checks={}; runtime=json.loads(Path(NEW_RUNTIME).read_bytes())
 historic=run(['nix-instantiate','--eval','--raw','--expr',f'(import {ROOT}/operations/forgejo/recovery/packages.nix {{ historical = true; }}).verifier.runtime.text'])
 assert Path(NEW_RUNTIME).read_bytes().replace(NEW_RUST.encode(),OLD_RUST.encode())==historic
 checks['runtime_diff_only_rust_store_path']=True
 historical_path=run(['nix-instantiate','--eval','--raw','--expr',f'(import {ROOT}/operations/forgejo/recovery/packages.nix {{ historical = true; }}).verifier.outPath']).decode()
 assert historical_path==OLD and not Path(OLD).exists()
 checks['historical_derivation_reproduced_but_output_absent']=True
 with tempfile.TemporaryDirectory(prefix='ci-validator-proof-') as tmp:
  tmp=Path(tmp);normalized=tmp/'normalized';shutil.copytree(NEW,normalized)
  for p in normalized.rglob('*'):
   assert not p.is_symlink()
   if p.is_file():
    mode=p.stat().st_mode;p.chmod(0o600);p.write_bytes(p.read_bytes().replace(NEW.encode(),OLD.encode()).replace(NEW_RUNTIME.encode(),OLD_RUNTIME.encode()));p.chmod(stat.S_IMODE(mode))
  nar=run(['nix','--extra-experimental-features','nix-command','nar','dump-path',str(normalized)])
  assert len(nar)==64992 and 'sha256-'+base64.b64encode(hashlib.sha256(nar).digest()).decode()=='sha256-shcQwaMMjlC0x4A8nDp1q9gXfN1E171tYsxXtv+s5H4='
  checks['normalized_validator_nar_matches_historical_content_not_derivation']=True
  inv=subprocess.run([NEW+'/bin/mrjam-validate','/arbitrary'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5)
  assert inv.returncode==1 and inv.stdout==b'' and json.loads(inv.stderr)=={'decision':'failed','code':'INVALID_INVOCATION'}
  checks['packaged_validator_closed_invalid_invocation']=True
  env={'PATH':runtime['path'],'LANG':'C','LC_ALL':'C','CARGO_HOME':str(tmp/'cargo-home'),'CARGO_TARGET_DIR':str(tmp/'target'),'RUSTC':runtime['tools']['rustc'],'RUSTDOC':runtime['tools']['rustdoc'],'CARGO_BUILD_JOBS':'2','CARGO_NET_OFFLINE':'true'}
  for key,version in [('rustc','1.99.1'),('cargo','1.99.1'),('node','v24.19.0'),('elm','0.19.1'),('elm_review','2.13.5'),('elm_test','0.19.1-revision17')]:
   output=run([runtime['tools'][key],'--version'],env=env).decode().strip();assert (output.split()[1] if key in ['cargo','rustc'] else output)==version
  checks['all_six_pinned_tool_versions_executed']=True
  crate=tmp/'crate';(crate/'src').mkdir(parents=True)
  (crate/'Cargo.toml').write_text('[package]\nname = "synthetic-validator-tool-proof"\nversion = "0.1.0"\nedition = "2024"\n')
  (crate/'src/lib.rs').write_text('#![forbid(unsafe_code)]\n\n/// Add two values.\n/// ```\n/// assert_eq!(synthetic_validator_tool_proof::add(2, 3), 5);\n/// ```\npub fn add(left: u32, right: u32) -> u32 {\n    left + right\n}\n\n#[cfg(test)]\nmod tests {\n    #[test]\n    fn exact_addition() {\n        assert_eq!(super::add(17, 25), 42);\n    }\n}\n')
  cargo=runtime['tools']['cargo']
  for args in [['generate-lockfile','--offline'],['fmt','--all','--check'],['clippy','--all-targets','--all-features','--frozen','--offline','--','-D','warnings','-F','unsafe_code'],['test','--frozen','--offline'],['build','--release','--frozen','--offline']]:run([cargo,*args],cwd=crate,env=env)
  checks['native_rust_fmt_clippy_unit_doctest_release_offline']=True
 import re
 receipt=json.loads((ROOT/'operations/forgejo/qualification-complete-chain-20261031.json').read_bytes())
 def find_paths(x):
  if isinstance(x,dict):
   for k,v in x.items():
    if k=='store_paths' and isinstance(v,list) and OLD in v:return v
    z=find_paths(v)
    if z:return z
  if isinstance(x,list):
   if OLD in x and all(isinstance(y,str) for y in x):return x
   for v in x:
    z=find_paths(v)
    if z:return z
 oldpaths=find_paths(receipt);assert oldpaths
 newpaths=Path('/nix/store/ypkc6s644xd79jlfwmx85gd8j2yfmldb-closure-info/store-paths').read_text().splitlines()
 mapped={p.replace(NEW,OLD).replace(NEW_RUST,OLD_RUST).replace(NEW_RUNTIME,OLD_RUNTIME) for p in newpaths}
 assert mapped==set(oldpaths),(len(mapped),len(oldpaths),mapped-set(oldpaths),set(oldpaths)-mapped)
 checks['closure_diff_only_validator_runtime_rust_roots']=True
 elm=json.loads((LOCAL/'validator-code/workflow-runner/elm-cache.lock.json').read_bytes())
 assert all(digest((LOCAL/'elm-cache'/p).read_bytes())==h for p,h in elm['files'].items())
 checks['all_449_elm_cache_inputs_exact']=True
 result={'schema_version':1,'scope':'local targeted qualification of interpreter repair; historical synthetic policy retained','checks':checks,'all_passed':all(checks.values()),'historical_output':OLD,'new_output':NEW,'historical_output_available':False,'historical_pipeline_rerun':False,'production_access':False,'independent_authority_established':False,'limits':['No new full 74-step application pipeline, real Forgejo dispatch or production installation claimed.','Normalized NAR proves unchanged verifier code after two explicit path substitutions; it is not the new derivation or an imported historical artifact.','The compiler installer is repaired with patchShebangs; the historical build was refused by the strict sandbox and privileged local access was unavailable.']}
 (LOCAL/'validator-targeted-result.json').write_text(json.dumps(result,sort_keys=True,indent=2)+'\n');print(json.dumps({'checks_passed':len(checks),'all_passed':True}))
if __name__=='__main__':main()
