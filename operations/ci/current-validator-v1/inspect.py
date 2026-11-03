"""Inspect only already selected public code; no build or governance write."""
import hashlib,json,subprocess,tempfile
from pathlib import Path
ROOT=Path.cwd()
BASE=ROOT/'.local/ci-artifact-recovery-20261102/proposal-base'
PUBLIC=Path('/nix/store/zjwbgmna6pyw7p151pzrgm20wi2jzfqv-mrjam-public-source-bundle-for-staging')
PATCH=ROOT/'operations/runtime/mateval-readiness-v1/readiness.patch'
FILES=('crates/server/src/database.rs','crates/server/tests/runtime_postgres.rs')
def sha(raw):return hashlib.sha256(raw).hexdigest()
def record(path):return {'path':str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),'sha256':sha(path.read_bytes())}
def main():
    left=json.loads((BASE/'manifest.json').read_bytes());right=json.loads((PUBLIC/'manifest.json').read_bytes())
    assert len(left['files'])==815 and left['files']==right['files']
    expected={entry['path'] for entry in left['files']}|{'manifest.json'}
    for directory in (BASE,PUBLIC):
        assert {str(p.relative_to(directory)) for p in directory.rglob('*') if p.is_file()}==expected
        for entry in left['files']:
            path=directory/entry['path'];assert not path.is_symlink()
            raw=path.read_bytes();assert len(raw)==entry['bytes'] and sha(raw)==entry['sha256']
    assert {k:v for k,v in left.items() if k!='rules_revision'}=={k:v for k,v in right.items() if k!='rules_revision'}
    assert left['rules_revision']=='eb71ffe5944943474c5ee483e66c270b5976ab90'
    assert right['rules_revision']=='93bd67666a3b4be9657c333931fa25b2359e165b'
    assert sha(PATCH.read_bytes())=='90d22b2216eb4496d3f518863d1f1ed8f41e524443b0cdd80c2463ea81fc48b4'
    publication=ROOT/'.local/deployment-20261101/final-source-publication-I-receipt-20261102.json'
    published=json.loads(publication.read_bytes());assert published['publication_succeeded'] is True and published['commit']=='22ede22314b9dda89f11383a5d4cd9ac3c01cdcd'
    entries=json.loads((ROOT/'.local/deployment-20261101/final-source-publication-I-20261102.manifest.json').read_bytes())
    assert next(item for item in entries if item['path']==str(PATCH.relative_to(ROOT)))['sha256']==sha(PATCH.read_bytes())
    patch_binary=Path('/run/current-system/sw/bin/patch').resolve(strict=True)
    before={name:sha((BASE/'sources/platform'/name).read_bytes()) for name in FILES}
    with tempfile.TemporaryDirectory(prefix='ci-public-patch-inspection-',dir=ROOT/'.local') as temporary:
        directory=Path(temporary)
        for name in FILES:
            target=directory/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((BASE/'sources/platform'/name).read_bytes())
        command=[str(patch_binary),'--fuzz=0','--batch','--forward','-p1','-i',str(PATCH)]
        result=subprocess.run(command,cwd=directory,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10,check=False)
        assert result.returncode==0 and not result.stderr
        assert {str(p.relative_to(directory)) for p in directory.rglob('*') if p.is_file()}==set(FILES)
        after={name:sha((directory/name).read_bytes()) for name in FILES}
    assert all(before[name]!=after[name] for name in FILES)
    policy=json.loads((ROOT/'.local/ci-artifact-recovery-20261102/policy-base.json').read_bytes())
    artifacts=json.loads((ROOT/'operations/hosts/mrjam-vps/application-artifacts.json').read_bytes())['outputs']
    server=artifacts['server'];assert server['store_path']=='/nix/store/wasrcrd9a76d1gpzzrhs0qkxbdqzwdrw-mrjam-server-mateval-typed-readiness-1'
    assert sha((Path(server['store_path'])/'artifact.json').read_bytes())==server['manifest_sha256']
    assert sha((Path(server['store_path'])/'bin/mrjam-server').read_bytes())==server['executable_sha256']['bin/mrjam-server']
    value={'schema_version':1,'date':'2026-11-03','scope':'source-and-recipe-choice-only','production_access':False,'build_performed':False,'private_histories_read':False,'governance_modified':False,
      'rules':{'accepted_main':left['rules_revision'],'proposed_not_adopted':'b02bdf1b5d63dcf0e0610723788a7ca7e384932c','historical_fixture_not_production':right['rules_revision']},
      'public_selection':{'files':815,'all_names_sizes_hashes_and_bytes_identical':True,'base_manifest':record(BASE/'manifest.json'),'qualified_public_manifest':record(PUBLIC/'manifest.json'),'historical_public_scope':record(ROOT/'operations/forgejo/STAGING-SOURCES.org'),'historical_qualification':record(ROOT/'operations/forgejo/qualification-staging-20261031.json'),'recovery_review':record(ROOT/'operations/forgejo/review-artifact-recovery-20261102.json'),'no_additional_bundle_blob_selected':True},
      'original_git_sources':[{key:item[key] for key in ('id','repository','revision','tree_sha')} for item in policy['sources']],
      'compiled_tree_overlay':{'repository':'MrJ-am/vps-infrastructure','publication':record(publication),'revision':published['commit'],'patch':record(PATCH),'changed_files':[{'path':name,'base_sha256':before[name],'compiled_sha256':after[name]} for name in FILES],'inspection_patch_binary':record(patch_binary),'inspection_fuzz':0,'original_git_tree_not_relabelled':True},
      'current_artifact_baseline':{key:value for key,value in artifacts.items() if key=='server' or key.startswith('frontend_')},
      'outside_existing_three_artifact_protocol':[key for key in artifacts if key!='server' and not key.startswith('frontend_')],
      'limitations':['Public status is the exact previously qualified selection, not a claim that whole private repository histories are public.','The patch produces a derived compilation tree; its files are not unchanged blobs of the original platform commit.','No new validator output or result has been produced; p249 and 93bd remain historical synthetic artifacts.','A future rebuilt ELF/archive has its own hashes until byte equality with the current artifact is actually measured.']}
    output=ROOT/'operations/ci/current-validator-v1/source-choice-20261103.json';output.write_text(json.dumps(value,sort_keys=True,indent=2)+'\n')
    print(json.dumps(record(output),sort_keys=True))
if __name__=='__main__':main()
