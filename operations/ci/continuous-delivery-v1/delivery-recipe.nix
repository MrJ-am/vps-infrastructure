# Explicit evaluator inventory, qualified against the installed generation.
# No whole-workspace inclusion and no private exports, credentials or logs.
{pkgs ? import /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source {}}:
let
  root=../../..;
  files=builtins.fromJSON (builtins.readFile ./delivery-recipe-files.json);
  inputs=map builtins.storePath (builtins.fromJSON (builtins.readFile ./delivery-recipe-evaluation-inputs.json));
  snapshots=map (name: {
    destination=".local/deployment-20261101/${name}";
    source=builtins.path {path=root+("/.local/deployment-20261101/"+name);inherit name;};
  }) ["accepted-e06-source" "aligned-proposal-003"];
  artifacts=map (name: {
    destination=".local/deployment-20261101/${name}";
    source=root+("/.local/deployment-20261101/"+name);
  }) ["accepted-e06-artifacts/server" "accepted-e06-artifacts/frontend.tar" "accepted-e06-artifacts/policy.json"
    "aligned-native-validation-002/artifacts/server" "aligned-native-validation-002/artifacts/frontend.tar"];
in assert pkgs.lib.all (name: builtins.match "(operations/[A-Za-z0-9_./-]+|flake.lock)" name!=null
  && !(pkgs.lib.hasInfix ".." name) && !(pkgs.lib.hasInfix "__pycache__" name)) files;
pkgs.runCommand "mrjam-protected-delivery-recipe-1" {} ''
  mkdir -p "$out/evaluation-inputs"
  # The historical filtered schema source retained this EMPTY directory.
  # Preserve its NAR shape, never Python cache contents, to reproduce the
  # existing disabled bootstrap unit exactly.
  mkdir -p "$out/operations/deployment/audition-schema-v2/__pycache__"
  ${pkgs.lib.concatMapStringsSep "\n" (path: ''
    ln -s ${path} "$out/evaluation-inputs/$(basename '${path}')"
  '') inputs}
  ${pkgs.lib.concatMapStringsSep "\n" (name: ''
    mkdir -p "$out/$(dirname '${name}')"
    cp ${root+("/"+name)} "$out/${name}"
  '') files}
  ${pkgs.lib.concatMapStringsSep "\n" (item: ''
    mkdir -p "$out/$(dirname '${item.destination}')"
    cp -r ${item.source} "$out/${item.destination}"
  '') (snapshots++artifacts)}
  cp ${./delivery-recipe-files.json} "$out/code-inventory.json"
''
