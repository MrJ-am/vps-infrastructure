{pkgs ? import /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source {}}:
let
  recipe=builtins.storePath /nix/store/gkh62splfw48h2hh7wbfrbz8p4fmnlf1-mrjam-protected-delivery-recipe-1;
  candidate=builtins.storePath /nix/store/0l3mivhq0j2sz7jrsbrrw4q30kb8pkww-mrjam-delivery-candidate-e06f030310ae-green;
  nix=builtins.storePath /nix/store/i4bv0lvk0gfzllcy2kqgz3iam0aw4c4i-nix-2.34.8;
in pkgs.runCommand "mrjam-qualify-generation-builder-vps" {nativeBuildInputs=[pkgs.makeWrapper];} ''
  mkdir -p "$out/bin" "$out/lib" "$out/inputs"
  cp ${./qualify-generation-builder-vps.py} "$out/lib/qualify.py"
  ln -s ${candidate} "$out/inputs/candidate"
  ln -s ${nix} "$out/inputs/nix"
  makeWrapper ${pkgs.python3}/bin/python3 "$out/bin/mrjam-qualify-generation-builder" \
    --add-flags '-I -S' --add-flags "$out/lib/qualify.py" \
    --set MRJAM_QUALIFICATION_RECIPE ${recipe}
''
