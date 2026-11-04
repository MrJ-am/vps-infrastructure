{pkgs ? import /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source {}}:
let
  runtime=import ./promotion-service.nix {inherit pkgs;};
  old=(import ./promotion-runtime-host.nix).toplevel;
  new=(import ./accepted-e06-promoted-host.nix).toplevel;
in pkgs.runCommand "mrjam-install-accepted-e06-plan" {nativeBuildInputs=[pkgs.makeWrapper];} ''
  mkdir -p "$out/lib" "$out/bin"
  cp ${./install-accepted-e06-plan.py} "$out/lib/main.py"
  substituteInPlace "$out/lib/main.py" --replace-fail '@runtime@' '${runtime}' \
    --replace-fail '@old@' '${old}' --replace-fail '@new@' '${new}'
  makeWrapper ${pkgs.python3}/bin/python3 "$out/bin/install-plan" --add-flags '-I -S' --add-flags "$out/lib/main.py"
''
