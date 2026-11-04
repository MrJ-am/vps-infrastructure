{pkgs ? import /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source {}}:
pkgs.runCommand "mrjam-merge-validated-proposal" {
  controller=builtins.storePath /nix/store/dlphwj3kmxmljjg4dj6flihqah9jghgy-mrjam-protected-admission-controller-1;
  anchor=builtins.storePath /nix/store/ixhqrvgq1vixg0g0fc01lwkdprxxkmn7-mrjam-validation-admission-control-1;
  nativeBuildInputs=[pkgs.makeWrapper];
} ''
  mkdir -p "$out/lib" "$out/bin"
  cp ${./forge_proposal.py} "$out/lib/forge_proposal.py"
  cp ${./forge_review.py} "$out/lib/forge_review.py"
  cp ${./forge_merge.py} "$out/lib/forge_merge.py"
  cp ${./delivery_roles.py} "$out/lib/delivery_roles.py"
  cp ${./merge-validated-proposal.py} "$out/lib/main.py"
  makeWrapper ${pkgs.python3}/bin/python3 "$out/bin/merge" --add-flags '-I -S' --add-flags "$out/lib/main.py" \
    --set MRJAM_MIRROR_GIT ${pkgs.git}/bin/git
''
