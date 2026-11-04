{pkgs ? import /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source {}}:
pkgs.runCommand "mrjam-activate-admission-controller" {nativeBuildInputs=[pkgs.makeWrapper];} ''
  mkdir -p "$out/lib" "$out/bin"
  cp ${./activate-admission-controller.py} "$out/lib/main.py"
  substituteInPlace "$out/lib/main.py" --replace-fail '@activation-driver@' '${./activate-intake-prepare.py}'
  makeWrapper ${pkgs.python3}/bin/python3 "$out/bin/activate" --add-flags '-I -S' --add-flags "$out/lib/main.py"
''
