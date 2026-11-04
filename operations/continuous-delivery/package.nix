{ pkgs ? import ../forgejo/locked-toolchain.nix { } }:
pkgs.runCommand "mrjam-continuous-delivery" {
  nativeBuildInputs = [ pkgs.makeWrapper ];
} ''
  mkdir -p "$out/bin" "$out/operations/continuous-delivery" "$out/operations/builds" "$out/operations/forgejo"
  cp ${./ci.py} "$out/operations/continuous-delivery/ci.py"
  cp ${./deploy.py} "$out/operations/continuous-delivery/deploy.py"
  cp ${./server.nix} "$out/operations/continuous-delivery/server.nix"
  cp ${./test_delivery.py} "$out/operations/continuous-delivery/test_delivery.py"
  cp ${../forgejo/locked-toolchain.nix} "$out/operations/forgejo/locked-toolchain.nix"
  cp ${../builds/toolchains.nix} "$out/operations/builds/toolchains.nix"
  cp ${../builds/toolchains.lock.json} "$out/operations/builds/toolchains.lock.json"
  cp ${../../flake.lock} "$out/flake.lock"
  makeWrapper ${pkgs.python3}/bin/python3 "$out/bin/mrjam-ci" \
    --add-flags "$out/operations/continuous-delivery/ci.py" \
    --prefix PATH : ${pkgs.lib.makeBinPath [ pkgs.nix pkgs.git pkgs.curl pkgs.bash pkgs.coreutils ]}
  makeWrapper ${pkgs.python3}/bin/python3 "$out/bin/mrjam-delivery" \
    --add-flags "$out/operations/continuous-delivery/deploy.py" \
    --prefix PATH : ${pkgs.lib.makeBinPath [ pkgs.systemd pkgs.curl pkgs.coreutils ]}
''
