{ policyFile, dependencies, probe ? "build"
, pkgs ? import /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source {}
}:
let
  oldRuntime=/nix/store/0py92lckwf8la1w2pq6d0cgd42xnpywr-mrjam-verifier-runtime.json;
  text=builtins.readFile oldRuntime;
  policy=pkgs.writeText "mrjam-vise-source-policy.json" (builtins.readFile policyFile);
  runtime=pkgs.writeText "mrjam-vise-build-probe-runtime.json" (builtins.appendContext
    (builtins.toJSON ((builtins.fromJSON (builtins.unsafeDiscardStringContext text))//{
      policy=toString policy;vise_dependencies=toString (builtins.storePath dependencies);
      vise_schema="${../schema-v1.sql}";
      vise_adopt_role="${../adopt-runtime-role.sql}";
      vise_adoption_check="${../check_adoption.py}";
      vise_schema_contract="${../schema-contract.json}";
      vise_runtime_entry="${./runtime_entry.py}";
      vise_api_tests="${builtins.storePath /nix/store/a46dz5ayfq3h5rksc6h6bsa5blzdnj40-mrjam-vise-0.2.0-8c8ef66f943c-tests}/api-tests.mjs";
    })) (builtins.getContext text));
in assert builtins.elem probe ["build" "database" "runtime" "validation"];
pkgs.runCommand "mrjam-vise-isolated-${probe}-probe-1" {
  nativeBuildInputs=[pkgs.python3 pkgs.makeWrapper];passthru={inherit runtime policy;};
} ''
  mkdir -p "$out/bin" "$out/lib"
  cp ${./build_stage.py} "$out/lib/build_stage.py"
  cp ${./source_policy.py} "$out/lib/source_policy.py"
  cp ${./source_scope.py} "$out/lib/source_scope.py"
  cp ${./dependency_binding.py} "$out/lib/dependency_binding.py"
  cp ${./synthetic_database.py} "$out/lib/synthetic_database.py"
  cp ${./runtime_stage.py} "$out/lib/runtime_stage.py"
  cp ${./artifacts.py} "$out/lib/artifacts.py"
  cp ${./authority_profile.py} "$out/lib/authority_profile.py"
  cp ${builtins.storePath /nix/store/p2494a4mh5nsp77sfzrfd8zhinz34bmp-mrjam-validate}/lib/sandbox.py "$out/lib/sandbox.py"
  substitute ${if probe == "build" then ./build-probe.py else if probe == "database" then ./database-probe.py else if probe == "runtime" then ./runtime-probe.py else ./validate.py} "$out/lib/probe.py" --replace-fail '@runtime@' '${runtime}'
  makeWrapper ${pkgs.python3}/bin/python3 "$out/bin/mrjam-validate" \
    --add-flags '-I -S' --add-flags "$out/lib/probe.py"
  python3 -I -S - "$out/lib" <<'PY'
  import ast,pathlib,sys
  root=pathlib.Path(sys.argv[1])
  for p in root.glob('*.py'):ast.parse(p.read_bytes())
  sys.path.insert(0,str(root));import source_policy
  source_policy.checked_policy(source_policy.read_json(pathlib.Path('${policy}')))
  PY
''
