{pkgs ? import /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source {}}:
let recipe=import ./delivery-recipe.nix {inherit pkgs;};
in pkgs.runCommand "mrjam-vise-backup-host-recipe-1" {} ''
  mkdir "$out"
  cp -r ${recipe}/. "$out/"
  chmod u+w "$out/operations/ci/continuous-delivery-v1"
  cp ${./vise-backup-host.nix} "$out/operations/ci/continuous-delivery-v1/vise-backup-host.nix"
''
