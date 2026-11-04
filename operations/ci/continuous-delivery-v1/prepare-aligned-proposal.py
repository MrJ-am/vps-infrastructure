"""Prepare the reconciled public-source proposal, without remote mutation."""
from pathlib import Path
import hashlib,importlib.util,json,shutil,tomllib
import source_snapshot as snapshot

BASE_DIGEST='8bf05fb9065a4c91e565ec0d37f24f2c556f315109823ccdef95c6354b423d6a'
REVISION='5a05461e9e3eb7cf77e99b85ae8d49630f13004d'
ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent

def sha(raw):return hashlib.sha256(raw).hexdigest()
def write(path,value):path.write_text(json.dumps(value,sort_keys=True,indent=2)+'\n')

def main():
    base=ROOT/'.local/ci-artifact-recovery-20261102/proposal-base'
    out=ROOT/'.local/deployment-20261101/aligned-proposal-003'
    raw=(base/'manifest.json').read_bytes();assert sha(raw)==BASE_DIGEST
    original=json.loads(raw);out.mkdir(mode=0o700)
    # Every inherited selected file must still match the audited manifest.
    for item in original['files']:
        relative=item['path']
        assert not Path(relative).is_absolute() and '..' not in Path(relative).parts
        src=base/relative;assert src.is_file() and not src.is_symlink()
        data=src.read_bytes();assert len(data)==item['bytes'] and sha(data)==item['sha256']
        target=out/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    policy=json.loads((HERE.parent/'current-validator-v1/policy.json').read_bytes())
    policy.pop('readiness_overlay');policy['schema_version']=1
    platform=next(x for x in policy['sources'] if x['id']=='platform')
    reader=snapshot.NativeObjects(ROOT/'.local/deployment-20261101/private-histories-20261102/bare/mrjam-plateforme.git',shutil.which('git'))
    tree=snapshot.complete_tree(reader,REVISION)
    spec=importlib.util.spec_from_file_location('protected_tree_gate','/nix/store/26qr08ambmn7g5dccqbr8q7aqkvcd92f-check_git_tree.py')
    gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
    prefix=platform['root']+'/'
    selected={x['path'][len(prefix):] for x in original['files'] if x['path'].startswith(prefix)}
    selected|={e['path'] for e in tree['tree'] if e['type']=='blob' and e['path'].startswith(('crates/identity/','crates/identity-deletion/')) and (e['path'].endswith('.rs') or e['path'].endswith('/Cargo.toml'))}
    selected|={e['path'] for e in tree['tree'] if e['type']=='blob' and gate.active_configuration(e['path'])}
    assert not [e['path'] for e in tree['tree'] if e['type']=='blob' and e['path'].endswith('.rs') and e['path'] not in selected]
    blobs=snapshot.select_blobs(reader,tree,lambda p:p in selected);assert set(blobs)==selected
    for name,data in blobs.items():
        path=out/platform['root']/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    platform.update(revision=REVISION,tree_sha=tree['sha'])
    write(out/platform['tree_json'],tree)
    members=tomllib.loads(blobs['Cargo.toml'].decode())['workspace']['members']
    expected={'crates/audition','crates/log','crates/server','crates/identity','crates/identity-deletion','components/mateval','components/vision'}
    assert set(members)==expected and len(members)==len(expected)
    manifests=['Cargo.toml','Cargo.lock']+[m+'/Cargo.toml' for m in members]
    roots={x['id']:out/x['root'] for x in policy['sources']}
    def manifest_path(name):
        parts=name.split('/')
        return roots[parts[1]]/Path(*parts[2:]) if parts[0]=='components' else roots['platform']/name
    policy['rust_manifests']={name:sha(manifest_path(name).read_bytes()) for name in manifests}
    manifest={'schema_version':1,'rules_revision':policy['rules_revision'],'files':[
        {'path':str(p.relative_to(out)),'bytes':p.stat().st_size,'sha256':sha(p.read_bytes())}
        for p in sorted(out.rglob('*')) if p.is_file()]}
    write(out/'manifest.json',manifest);write(HERE/'aligned-policy.json',policy)
    write(HERE/'qualification-aligned-proposal-003.json',{
        'schema_version':1,'scope':'prepared-not-admitted','files':len(manifest['files']),
        'proposal_sha256':sha((out/'manifest.json').read_bytes()),
        'policy_sha256':sha((HERE/'aligned-policy.json').read_bytes()),
        'platform_revision':REVISION,'platform_tree':tree['sha'],
        'rust_members':members,'production_activation':False})
    print(json.dumps({'files':len(manifest['files']),'proposal_sha256':sha((out/'manifest.json').read_bytes())}))

if __name__=='__main__':main()
