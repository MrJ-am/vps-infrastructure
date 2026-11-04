{pkgs ? import /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source {}}:
pkgs.runCommand "mrjam-activate-acceptance-services" {
  system=(import ./acceptance-host.nix).toplevel;
  nativeBuildInputs=[pkgs.makeWrapper];
} ''
  mkdir -p "$out/lib" "$out/bin"
  cp ${./activate-acceptance-services.py} "$out/lib/main.py"
  makeWrapper ${pkgs.python3}/bin/python3 "$out/bin/activate" --add-flags '-I -S' --add-flags "$out/lib/main.py"
''
