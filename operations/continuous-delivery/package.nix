{ pkgs ? import ../forgejo/locked-toolchain.nix { } }:
pkgs.runCommand "mrjam-continuous-delivery" {
  nativeBuildInputs = [ pkgs.makeWrapper ];
} ''
  mkdir -p "$out/bin" "$out/operations/continuous-delivery" "$out/operations/builds" "$out/operations/forgejo"
  cp -R ${builtins.path { path = ./.; name = "delivery-engine-source"; filter = path: type: builtins.baseNameOf path != "__pycache__"; }}/. "$out/operations/continuous-delivery/"
  cp ${../forgejo/locked-toolchain.nix} "$out/operations/forgejo/locked-toolchain.nix"
  cp ${../builds/toolchains.nix} "$out/operations/builds/toolchains.nix"
  cp ${../builds/toolchains.lock.json} "$out/operations/builds/toolchains.lock.json"
  cp ${../../flake.lock} "$out/flake.lock"
  makeWrapper ${pkgs.python3}/bin/python3 "$out/bin/mrjam-ci" \
    --add-flags "$out/operations/continuous-delivery/ci.py" \
    --prefix PATH : ${pkgs.lib.makeBinPath [ pkgs.nix pkgs.git pkgs.curl pkgs.bash pkgs.coreutils ]}
  makeWrapper ${pkgs.python3}/bin/python3 "$out/bin/mrjam-delivery" \
    --add-flags "$out/operations/continuous-delivery/deploy.py" \
    --prefix PATH : ${pkgs.lib.makeBinPath [ pkgs.systemd pkgs.curl pkgs.coreutils pkgs.nix pkgs.util-linux ]}
''
