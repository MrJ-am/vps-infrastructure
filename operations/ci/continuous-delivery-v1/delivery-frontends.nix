# Content-only packaging. The protected caller supplies verified bindings.
{ pkgs ? import ../../forgejo/locked-toolchain.nix {}, archive, expectedSha256,
  proposal, reportPolicy, reportPolicySha256, toolchainsSha256 }:
assert builtins.all (value: builtins.match "[0-9a-f]{64}" value != null)
  [expectedSha256 proposal reportPolicySha256 toolchainsSha256];
pkgs.runCommand "mrjam-delivery-frontends-${builtins.substring 0 12 proposal}" {
  nativeBuildInputs=[pkgs.python3];
  outputs=["out" "audition" "log" "logique" "mateval" "vision" "style" "logo"];
} ''
  cp ${./delivery_frontends.py} delivery_frontends.py
  python3 -I -S - "$PWD" <<'PY'
import hashlib,json,os,pathlib,sys
sys.path.insert(0,sys.argv[1]);import delivery_frontends as D
policy_raw=pathlib.Path('${reportPolicy}').read_bytes()
assert hashlib.sha256(policy_raw).hexdigest()=='${reportPolicySha256}'
policy=json.loads(policy_raw,object_pairs_hook=D.unique)
sources={item['id']:item['revision'] for item in policy['sources']}
styles={item['id']:sources[item['style_source']] for item in policy['frontends']}
assert len(sources)==len(policy['sources']) and len(styles)==len(policy['frontends'])
files=D.validate(pathlib.Path('${archive}').read_bytes(),archive_sha256='${expectedSha256}',
                 proposal='${proposal}',sources=sources,styles=styles,
                 toolchains_sha256='${toolchainsSha256}')
inventory={}
for group,items in sorted(files.items()):
    target=pathlib.Path(os.environ['logo' if group=='style-logo' else group]);target.mkdir()
    for name,data in sorted(items.items()):
        path=target/name;path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as output:output.write(data)
        path.chmod(0o444)
    inventory[group]={'store_path':str(target),'manifest_sha256':D.digest(items['artifact.json']),
                      'files':len(items)}
out=pathlib.Path(os.environ['out']);out.mkdir()
(out/'inventory.json').write_text(json.dumps({'schema_version':1,'proposal_sha256':'${proposal}',
    'frontend_archive_sha256':'${expectedSha256}','outputs':inventory,
    'deployment_authorized':False},sort_keys=True)+'\n')
PY
''
