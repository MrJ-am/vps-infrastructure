# Rules are exported from an exact Git commit by the protected preparer.
# This constructor binds bytes and revision, but grants no adoption authority.
{rulesSource, rulesRevision, policyFile, dependencies,
 pkgs ? import /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source {}}:
let
  source=builtins.path {path=rulesSource;name="mrjam-vise-canonical-rules";};
  provenance=builtins.fromJSON (builtins.readFile (source+"/provenance.json"));
  exported=builtins.fromJSON (builtins.readFile (source+"/export.json"));
  report=builtins.fromJSON (builtins.readFile policyFile);
  modules=["build_stage.py" "source_policy.py" "source_scope.py" "dependency_binding.py"
    "synthetic_database.py" "runtime_stage.py" "artifacts.py" "authority_profile.py" "sandbox.py"];
  required=(map (name: "delivery/"+name) (modules++["validate.py" "runtime_entry.py"
    "schema-v1.sql" "adopt-runtime-role.sql" "check_adoption.py" "schema-contract.json" "api-tests.mjs"
    "test_source_scope.py" "test_artifacts.py"]))++["sources.lock.json"];
  valid=row: builtins.elem row.path required
    && builtins.hashFile "sha256" (source+"/${row.path}")==row.sha256
    && builtins.stringLength (builtins.readFile (source+"/${row.path}"))==row.bytes;
  file=name: builtins.path {path=source+"/delivery/${name}";inherit name;};
  apiTests=pkgs.runCommand "mrjam-vise-canonical-api-tests" {} ''
    mkdir "$out";cp ${file "api-tests.mjs"} "$out/api-tests.mjs"
  '';
  oldText=builtins.readFile /nix/store/0py92lckwf8la1w2pq6d0cgd42xnpywr-mrjam-verifier-runtime.json;
  policy=pkgs.writeText "mrjam-vise-canonical-policy.json" (builtins.readFile policyFile);
  runtime=pkgs.writeText "mrjam-vise-canonical-runtime.json" (builtins.appendContext
    (builtins.toJSON ((builtins.fromJSON (builtins.unsafeDiscardStringContext oldText))//{
      policy=toString policy;vise_dependencies=toString (builtins.storePath dependencies);
      vise_schema=toString (file "schema-v1.sql");vise_adopt_role=toString (file "adopt-runtime-role.sql");
      vise_adoption_check=toString (file "check_adoption.py");vise_schema_contract=toString (file "schema-contract.json");
      vise_runtime_entry=toString (file "runtime_entry.py");vise_api_tests="${apiTests}/api-tests.mjs";
    })) (builtins.getContext oldText));
in assert builtins.match "[0-9a-f]{40}" rulesRevision!=null;
assert rulesRevision!="0000000000000000000000000000000000000000";
assert exported.revision==rulesRevision && exported.repository=="MrJ-am/mrjam-validation";
assert report.rules_revision==rulesRevision && report.profile=="vise-v1";
assert provenance.profile=="vise-v1" && provenance.deployment_authorized==false;
assert builtins.sort builtins.lessThan (map (row: row.path) provenance.files)==builtins.sort builtins.lessThan required;
assert builtins.all valid provenance.files;
pkgs.runCommand "mrjam-vise-canonical-validator-1" {
  nativeBuildInputs=[pkgs.python3 pkgs.makeWrapper];
  passthru={inherit runtime policy source rulesRevision;};
} ''
  mkdir -p "$out/bin" "$out/lib"
  ${pkgs.lib.concatMapStringsSep "\n" (name: "cp ${file name} \"$out/lib/${name}\"") modules}
  substitute ${file "validate.py"} "$out/lib/probe.py" --replace-fail '@runtime@' '${runtime}'
  cp ${source}/export.json "$out/rules-export.json"
  cp ${source}/provenance.json "$out/rules-provenance.json"
  makeWrapper ${pkgs.python3}/bin/python3 "$out/bin/mrjam-validate" \
    --add-flags '-I -S' --add-flags "$out/lib/probe.py"
  python3 -I -S - "$out/lib" <<'PY'
  import ast,pathlib,sys
  root=pathlib.Path(sys.argv[1])
  for path in root.glob('*.py'):ast.parse(path.read_bytes())
  sys.path.insert(0,str(root));import source_policy
  source_policy.checked_policy(source_policy.read_json(pathlib.Path('${policy}')))
  PY
''
