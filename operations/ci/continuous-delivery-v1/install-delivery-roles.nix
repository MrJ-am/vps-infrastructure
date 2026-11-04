{pkgs ? import /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source {}}:
pkgs.runCommand "mrjam-install-delivery-roles" {
  bootstrap=builtins.storePath /nix/store/8pkxq7pahlmhlmf6v890q2ica69cflsy-mrjam-forgejo-technical-bootstrap-1;
  nativeBuildInputs=[pkgs.python3 pkgs.makeWrapper];
} ''
  mkdir -p "$out/lib" "$out/bin"
  cp ${./install-delivery-roles.py} "$out/lib/main.py"
  cp ${./delivery_roles.py} "$out/lib/delivery_roles.py"
  cp ${./source_snapshot.py} "$out/lib/source_snapshot.py"
  substituteInPlace "$out/lib/main.py" --replace-fail '@credential-helpers@' '${../activation-v1/credentials.py}'
  makeWrapper ${pkgs.python3}/bin/python3 "$out/bin/install" --add-flags '-I -S' --add-flags "$out/lib/main.py"
  python3 -I -S - "$out/lib" <<'PY'
  import ast,pathlib,sys
  for p in pathlib.Path(sys.argv[1]).glob('*.py'):ast.parse(p.read_bytes())
  PY
''
