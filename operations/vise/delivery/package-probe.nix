{ policyFile, dependencies, package
, pkgs ? import /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source {} }:
let
  base=import ./build-probe.nix {inherit policyFile dependencies pkgs;probe="runtime";};
  content=if builtins.isAttrs package then package else builtins.storePath package;
in pkgs.runCommand "mrjam-vise-packaged-runtime-probe-1" {
  nativeBuildInputs=[pkgs.python3 pkgs.makeWrapper];
  passthru={inherit (base) runtime;};
} ''
  mkdir -p "$out/lib" "$out/bin"
  cp ${base}/lib/*.py "$out/lib/"
  chmod u+w "$out/lib/probe.py"
  substitute ${./package-probe.py} "$out/lib/probe.py" \
    --replace-fail '@runtime@' '${base.runtime}' --replace-fail '@package@' '${content}'
  makeWrapper ${pkgs.python3}/bin/python3 "$out/bin/mrjam-validate" \
    --add-flags '-I -S' --add-flags "$out/lib/probe.py"
  python3 -I -S - "$out/lib/probe.py" <<'PY'
  import ast,pathlib,sys
  ast.parse(pathlib.Path(sys.argv[1]).read_bytes())
  PY
''
