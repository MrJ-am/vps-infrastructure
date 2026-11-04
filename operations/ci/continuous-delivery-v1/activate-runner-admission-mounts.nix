{pkgs ? import /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source {}}:
pkgs.runCommand "mrjam-activate-runner-admission-mounts" {
  driver=builtins.storePath /nix/store/5gxlbfkdcvzx3dsnlkrqpmc5gczr8pp9-mrjam-activate-runner-policy-directory;
  nativeBuildInputs=[pkgs.makeWrapper];
} ''
  mkdir -p "$out/lib" "$out/bin"
  cp ${./activate-runner-admission-mounts.py} "$out/lib/main.py"
  makeWrapper ${pkgs.python3}/bin/python3 "$out/bin/activate" --add-flags '-I -S' --add-flags "$out/lib/main.py"
''
