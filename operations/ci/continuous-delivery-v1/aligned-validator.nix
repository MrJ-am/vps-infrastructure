# Proposed control package, never selected by candidate input or activated here.
{ pkgs ? import ../../forgejo/locked-toolchain.nix {}
, policyFile ? ./aligned-policy.json
, cargoVendor ? builtins.storePath /nix/store/ivbh7z3jxnh58sc15klrmhg4z8jhiqf4-cargo-vendor-dir
}:
let
  base = builtins.storePath /nix/store/p2494a4mh5nsp77sfzrfd8zhinz34bmp-mrjam-validate;
  oldRuntime = builtins.storePath /nix/store/0py92lckwf8la1w2pq6d0cgd42xnpywr-mrjam-verifier-runtime.json;
  vendor = cargoVendor;
  policy = pkgs.writeText "mrjam-aligned-validator-policy.json" (builtins.readFile policyFile);
  runtimeText = builtins.readFile oldRuntime;
  runtime = pkgs.writeText "mrjam-aligned-validator-runtime.json" (builtins.appendContext
    (builtins.toJSON ((builtins.fromJSON (builtins.unsafeDiscardStringContext runtimeText)) // {
      policy = toString policy; cargo_vendor = toString vendor;
    })) (builtins.getContext runtimeText));
in pkgs.runCommand "mrjam-validate-aligned-workspace-1" {
  nativeBuildInputs = [ pkgs.python3 ]; passthru = { inherit runtime policy vendor; };
} ''
  mkdir -p "$out"
  cp -a ${base}/. "$out/"
  chmod -R u+w "$out"
  substituteInPlace "$out/bin/mrjam-validate" --replace-fail '${base}/lib/runner.py' "$out/lib/runner.py"
  substituteInPlace "$out/lib/runner.py" --replace-fail '${oldRuntime}' '${runtime}'
  python3 -I -S - "$out/lib" <<'PY'
  import ast,pathlib,sys
  root=pathlib.Path(sys.argv[1])
  p=root/'policy.py';source=p.read_text()
  old='MEMBERS = ("crates/audition", "crates/log", "crates/server", "components/mateval", "components/vision")'
  new='MEMBERS = ("crates/audition", "crates/log", "crates/server", "crates/identity", "crates/identity-deletion", "components/mateval", "components/vision")'
  assert source.count(old)==1;p.write_text(source.replace(old,new))
  p=root/'runner.py';source=p.read_text()
  before='"elm-entrypoint-" + name + "-" + Path(target).stem'
  assert source.count(before)==1
  p.write_text(source.replace(before,before+'.lower()'))
  for p in root.glob('*.py'):ast.parse(p.read_bytes())
  sys.path.insert(0,str(root));import policy
  policy.checked_policy(policy.read_json(pathlib.Path('${policy}')))
  PY
''
