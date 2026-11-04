{ pkgs ? import ../../forgejo/locked-toolchain.nix {} }:
pkgs.runCommand "mrjam-capture-aligned-delivery-1" {nativeBuildInputs=[pkgs.makeWrapper];} ''
  mkdir -p "$out/bin" "$out/lib"
  cp ${./delivery_capture.py} "$out/lib/delivery_capture.py"
  cp ${./capture-aligned-delivery.py} "$out/lib/capture.py"
  substituteInPlace "$out/lib/capture.py" --replace-fail '@capture-lib@' "$out/lib"
  makeWrapper ${pkgs.python3}/bin/python3 "$out/bin/mrjam-capture-aligned-delivery" \
    --add-flags '-I -S' --add-flags "$out/lib/capture.py"
''
