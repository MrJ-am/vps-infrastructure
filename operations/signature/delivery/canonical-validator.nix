# Qualification package only: adoption remains a separate protected operation.
{ rulesRoot, policyFile
, pkgs ? import /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source {}
, cargoVendor ? builtins.storePath /nix/store/ivbh7z3jxnh58sc15klrmhg4z8jhiqf4-cargo-vendor-dir
}:
let
  base = builtins.storePath /nix/store/p2494a4mh5nsp77sfzrfd8zhinz34bmp-mrjam-validate;
  oldRuntime = builtins.storePath /nix/store/0py92lckwf8la1w2pq6d0cgd42xnpywr-mrjam-verifier-runtime.json;
  support = import ./support.nix { inherit rulesRoot pkgs; };
  policy = pkgs.writeText "mrjam-signature-platform-policy.json" (builtins.readFile policyFile);
  runtimeText = builtins.readFile oldRuntime;
  runtime = pkgs.writeText "mrjam-signature-platform-runtime.json" (builtins.appendContext
    (builtins.toJSON ((builtins.fromJSON (builtins.unsafeDiscardStringContext runtimeText)) // {
      policy = toString policy;
      cargo_vendor = toString cargoVendor;
      signature_python = "${support.python}/bin/python3";
      signature_support = toString support;
    })) (builtins.getContext runtimeText));
  files = [ "runner.py" "policy.py" "frontend_assembly.py" "sandbox.py" "consumer_identity.py" ];
in pkgs.runCommand "mrjam-signature-platform-validator-1" {
  nativeBuildInputs = [ pkgs.python3 ];
  passthru = { inherit runtime policy support; };
} ''
  mkdir -p "$out"
  cp -a ${base}/. "$out/"
  chmod -R u+w "$out"
  ${pkgs.lib.concatMapStringsSep "\n" (name: ''
    cp ${rulesRoot + ("/workflow-runner/" + name)} "$out/lib/${name}"
  '') files}
  substituteInPlace "$out/bin/mrjam-validate" --replace-fail '${base}/lib/runner.py' "$out/lib/runner.py"
  substituteInPlace "$out/lib/runner.py" --replace-fail '@runtime@' '${runtime}'
  python3 -I -S - "$out/lib" <<'PY'
  import ast,pathlib,sys
  root=pathlib.Path(sys.argv[1])
  for source in root.glob('*.py'):ast.parse(source.read_bytes())
  sys.path.insert(0,str(root));import policy
  policy.checked_policy(policy.read_json(pathlib.Path('${policy}')))
  PY
''
