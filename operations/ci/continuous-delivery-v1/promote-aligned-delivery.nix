{ pkgs ? import ../../forgejo/locked-toolchain.nix {} }:
pkgs.runCommand "mrjam-promote-reviewed-delivery-1" {nativeBuildInputs=[pkgs.makeWrapper];} ''
  mkdir -p "$out/bin" "$out/lib"
  cp ${./stage-aligned-delivery.py} "$out/lib/stage.py"
  cp ${./promote-aligned-delivery.py} "$out/lib/promote.py"
  substituteInPlace "$out/lib/promote.py" --replace-fail '@delivery-lib@' "$out/lib"
  makeWrapper ${pkgs.python3}/bin/python3 "$out/bin/mrjam-promote-reviewed-delivery" --add-flags '-I -S' --add-flags "$out/lib/promote.py"
''
