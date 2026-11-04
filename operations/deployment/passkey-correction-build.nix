# Fixed, already-built packages; this evaluation creates inactive unit files.
{ nixpkgs }:
let
  provisionPackage = builtins.storePath "/nix/store/13qs6kk65vss4k3mcb86aiv8nww1qazl-mrjam-kanidm-worker-provision-3";
  portalPackage = builtins.storePath "/nix/store/an04ifkrx986xh8j2ynlmgbqh10vdibi-mrjam-kanidm-passkey-portal-2";
  system = import (nixpkgs + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux";
    modules = [ ./credentials-v3/provisioning-unit.nix ./passkey-portal-v2/unit.nix ({...}: {
      system.stateVersion = "26.05";
      services.mrjamKanidmWorkerProvision = { enable = true; package = provisionPackage; };
      services.mrjamKanidmPasskeyPortal = { enable = true; package = portalPackage; };
    }) ];
  };
in {
  inherit provisionPackage portalPackage;
  provisionUnit = system.config.systemd.units."mrjam-kanidm-worker-provision.service".unit;
  portalUnit = system.config.systemd.units."mrjam-kanidm-passkey-portal.service".unit;
}
