# Synthetic local commit, real protected constructor and production trust anchor.
# No publication, signing, dispatch or activation is performed.
{ pkgs ? import ../../forgejo/locked-toolchain.nix {} }:
let
  fixture=../../../.local/deployment-20261101/generic-prepared-candidate-001;
  bindings=import ./proposal-bindings.nix {
    inherit pkgs;
    preparedSource=fixture+"/source";policyFile=fixture+"/policy.json";
    proposal="952f4611369b7a4faaa4566e81d96af60e78cfe6fac3a0f8cf03c5eaba221ae6";
  };
  nar=pkgs.runCommand "mrjam-synthetic-admission-validator-nar" {} ''
    ${pkgs.nix}/bin/nix-hash --type sha256 --base64 ${bindings.validator} > "$out"
  '';
  verifierNarHash="sha256-"+pkgs.lib.removeSuffix "\n" (builtins.readFile nar);
  control=import ./admission-package.nix {inherit pkgs bindings verifierNarHash;};
  installed=import ./admission-package.nix {inherit pkgs;};
in pkgs.runCommand "mrjam-generic-admission-constructor-qualification" {
  nativeBuildInputs=[pkgs.python3];
  seed=control.metadataSeed;
  source=bindings.source;
  newControl=control;
} ''
  mkdir "$out"
  python3 -I -S - "$out" <<'PY'
  import hashlib,json,os,pathlib,sys
  sys.path.insert(0,'${installed}/lib')
  import contract as C,admission_registry as R,admission_control as A
  record=C.parse(pathlib.Path('${control.recordFile}').read_bytes())
  anchor=C.parse(pathlib.Path(A.ANCHOR_PATH).read_bytes())
  def read(path,maximum=131072):
      # Inputs are immutable Nix build dependencies; UID mapping here differs
      # from the deployed root reader, whose metadata checks remain unchanged.
      raw=pathlib.Path(path).read_bytes();assert 0<len(raw)<=maximum
      copied=pathlib.Path(os.environ['seed'],C.sha(path.encode())+'.data').read_bytes()
      assert copied==raw
      return raw
  selected=R.resolve(record,'${bindings.proposal}',anchor,A.BUBBLEWRAP,read=read,now=anchor['not_before']+1)
  assert selected['authority']['sources']!=anchor['sources']
  for field in R.ANCHOR_FIELDS:assert selected['authority'][field]==anchor[field]
  for field in R.RECIPE_FIELDS:assert selected['producer'][field]==anchor['producer'][field]
  assert selected['authority']['verifier']=='${bindings.validator}'
  assert selected['authority']['verifier_nar_hash']=='${verifierNarHash}'
  manifest=pathlib.Path(os.environ['source'],'manifest.json').read_bytes()
  assert hashlib.sha256(manifest).hexdigest()=='${bindings.proposal}'
  result={'schema_version':1,'passed':True,'scope':'synthetic-candidate-real-admission-constructor',
      'proposal':'${bindings.proposal}','validator':'${bindings.validator}',
      'source':os.environ['source'],'control':os.environ['newControl'],
      'production_anchor_accepted':True,'fixed_identity_rules_and_recipes_preserved':True,
      'different_source_and_validator_bound':True,'public_metadata_documents':len(list(pathlib.Path(os.environ['seed']).iterdir())),
      'registry_published':False,'candidate_code_executed':False,'deployment_authorized':False}
  pathlib.Path(sys.argv[1],'result.json').write_text(json.dumps(result,sort_keys=True)+'\n')
  PY
''
