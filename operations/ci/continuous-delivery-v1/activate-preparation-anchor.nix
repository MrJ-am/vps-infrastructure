{pkgs ? import /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source {}}:
pkgs.runCommand "mrjam-activate-preparation-anchor" {
  targetSystem=builtins.storePath /nix/store/459b63mrbil3n5ya27d7w1x8vas4za3k-nixos-system-srv1982677-26.05pre-git;
  nativeBuildInputs=[pkgs.makeWrapper];
} ''
  mkdir -p "$out/lib" "$out/bin"
  ln -s "$targetSystem" "$out/system"
  cp ${./activate-preparation-anchor.py} "$out/lib/main.py"
  makeWrapper ${pkgs.python3}/bin/python3 "$out/bin/activate" --add-flags '-I -S' --add-flags "$out/lib/main.py"
''
