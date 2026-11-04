{ nixpkgs }:
let
  pkgs=import nixpkgs {system="x86_64-linux";};
  package=builtins.storePath "/nix/store/5yqv8fsy6qhw45qs53qnirib9vl3cjhq-mrjam-kanidm-worker-provision-2";
  system=import (nixpkgs+"/nixos/lib/eval-config.nix") {
    system="x86_64-linux";
    modules=[ ./credentials/provisioning-unit.nix ({...}:{
      system.stateVersion="26.05";
      services.mrjamKanidmWorkerProvision={enable=true;inherit package;};
    }) ];
  };
in {
  inherit package;
  unit=system.config.systemd.units."mrjam-kanidm-worker-provision.service".unit;
}
