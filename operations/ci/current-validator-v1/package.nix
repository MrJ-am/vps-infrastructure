{ pkgs ? import ../../forgejo/locked-toolchain.nix {} }:
let
  # Explicit control-code base, already reproduced and reviewed. Its old
  # synthetic policy is not selected or retained by the resulting runtime.
  base = builtins.storePath /nix/store/p2494a4mh5nsp77sfzrfd8zhinz34bmp-mrjam-validate;
  oldRuntime = builtins.storePath /nix/store/0py92lckwf8la1w2pq6d0cgd42xnpywr-mrjam-verifier-runtime.json;
  policy = pkgs.writeText "mrjam-current-validator-proposed-policy-v2.json" (builtins.readFile ./policy.json);
  contract = pkgs.writeText "mrjam-reviewed-readiness-overlay.json" (builtins.readFile ./overlay.json);
  patch = ../../runtime/mateval-readiness-v1/readiness.patch;
  runtimeText = builtins.readFile oldRuntime;
  runtime = pkgs.writeText "mrjam-current-validator-runtime-v1.json" (builtins.appendContext
    (builtins.toJSON ((builtins.fromJSON (builtins.unsafeDiscardStringContext runtimeText)) // { policy = toString policy; }))
    (builtins.getContext runtimeText));
in assert builtins.hashFile "sha256" patch == "90d22b2216eb4496d3f518863d1f1ed8f41e524443b0cdd80c2463ea81fc48b4";
pkgs.runCommand "mrjam-validate-current-readiness-1" { nativeBuildInputs = [ pkgs.python3 ]; passthru = { inherit runtime policy contract; }; } ''
  mkdir -p "$out"
  cp -a ${base}/. "$out/"
  chmod -R u+w "$out"
  mv "$out/lib/policy.py" "$out/lib/base_policy.py"
  cp ${./policy_v2.py} "$out/lib/policy.py"
  cp ${./readiness.py} "$out/lib/readiness.py"
  substituteInPlace "$out/lib/readiness.py" \
    --replace-fail '@contract@' '${contract}' \
    --replace-fail '@patch@' '${patch}' \
    --replace-fail '@patch-tool@' '${pkgs.patch}/bin/patch'
  substituteInPlace "$out/bin/mrjam-validate" --replace-fail '${base}/lib/runner.py' "$out/lib/runner.py"
  substituteInPlace "$out/lib/runner.py" --replace-fail '${oldRuntime}' '${runtime}'
  ${pkgs.python3}/bin/python3 -I -S - "$out/lib" <<'PY'
  import ast,pathlib,sys
  root=pathlib.Path(sys.argv[1]);path=root/'runner.py';source=path.read_text()
  changes={
      'import policy as rules': 'import policy as rules\nimport readiness',
      '        # No candidate Cargo configuration can redirect a compiler, registry,':
      '        self.steps.append({"name": readiness.apply(source, self.policy), "status": "passed"})\n        # No candidate Cargo configuration can redirect a compiler, registry,',
      '"elm-entrypoint-" + name + "-" + Path(target).stem':
      '"elm-entrypoint-" + name + "-" + Path(target).stem.lower()',
  }
  for before,after in changes.items():
      assert source.count(before)==1
      source=source.replace(before,after)
  path.write_text(source)
  for entry in root.glob('*.py'):ast.parse(entry.read_bytes())
  sys.path.insert(0,str(root));import policy
  policy.checked_policy(policy.read_json(pathlib.Path('${policy}')))
  PY
''
