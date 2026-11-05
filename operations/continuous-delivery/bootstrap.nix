{ pkgs ? import ../forgejo/locked-toolchain.nix { } }:
pkgs.runCommand "mrjam-delivery-bootstrap" { nativeBuildInputs = [ pkgs.makeWrapper ]; } ''
  mkdir -p "$out/bin" "$out/lib"
  cp ${./bootstrap.py} "$out/lib/bootstrap.py"
  makeWrapper ${pkgs.python3}/bin/python3 "$out/bin/mrjam-ci" \
    --add-flags "$out/lib/bootstrap.py ci" \
    --prefix PATH : ${pkgs.lib.makeBinPath [ pkgs.nix pkgs.git pkgs.curl pkgs.bash pkgs.coreutils ]}
  makeWrapper ${pkgs.python3}/bin/python3 "$out/bin/mrjam-delivery" \
    --add-flags "$out/lib/bootstrap.py delivery" \
    --prefix PATH : ${pkgs.lib.makeBinPath [ pkgs.nix pkgs.systemd pkgs.curl pkgs.coreutils pkgs.util-linux ]}
''
