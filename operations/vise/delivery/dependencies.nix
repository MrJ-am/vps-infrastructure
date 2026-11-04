# Trusted materialization only. No candidate Nix or package-manager lifecycle.
{ materialized
, pkgs ? import /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source {}
}:
let
  inputs=builtins.path {path=materialized;name="vise-qualified-materialization";};
  manifest="b0c8a52571c4e1c3b89b5c72b82f15a55bb968d4d1a1a95ca3c433c9ef2b651f";
in pkgs.runCommand "mrjam-vise-validation-dependencies-1" {
  nativeBuildInputs=[pkgs.python3];
  disallowedReferences=[inputs];
} ''
  python3 ${../verify_inputs.py} --inputs ${inputs} --manifest-sha256 ${manifest} \
    --source-lock ${../sources-adoption-20261101.lock.json}
  mkdir "$out"
  cp -r ${inputs}/cargo-vendor ${inputs}/node_modules ${inputs}/elm-home "$out/"
  python3 -I -S - ${inputs}/source "$out" <<'PY'
  import hashlib,json,pathlib,sys
  source=pathlib.Path(sys.argv[1]);out=pathlib.Path(sys.argv[2])
  names=['backend/Cargo.lock','package-lock.json','elm.json']
  package=json.loads((source/'package.json').read_bytes())
  fields=['dependencies','devDependencies','optionalDependencies','peerDependencies',
          'peerDependenciesMeta','overrides','workspaces','os','cpu']
  descriptor={'schema_version':1,'materialization_sha256':'${manifest}',
      'locks':{n:hashlib.sha256((source/n).read_bytes()).hexdigest() for n in names},
      'npm_dependency_fields':{k:package[k] for k in fields if k in package},
      'npm_lifecycle_scripts':False}
  (out/'descriptor.json').write_text(json.dumps(descriptor,sort_keys=True,separators=(',',':'))+'\n')
  PY
''
