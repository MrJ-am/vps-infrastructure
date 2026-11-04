# Add only the qualified read-only GitHub discovery timer to the live baseline.
let
  nixpkgs=/nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source;
  lib=(import nixpkgs {}).lib;
  baseline=import ../../vise/requalification-20261103/promoted.nix;
  addition=[./github-discovery-module.nix { services.mrjamGithubDiscovery.enable=true; }];
  evaluate=extra: (import (nixpkgs+"/nixos/lib/eval-config.nix") {
    system="x86_64-linux"; modules=baseline.modules++extra;
  }).config;
  before=evaluate []; after=evaluate addition;
  added=lib.subtractLists (builtins.attrNames before.systemd.units) (builtins.attrNames after.systemd.units);
  checks={
    baselineExact=toString before.system.build.toplevel=="/nix/store/17lw8y05pgzmcl9q6wvknbf7z1znajl9-nixos-system-srv1982677-26.05pre-git";
    assertionsPass=lib.all (a: a.assertion) after.assertions;
    onlyDiscoveryUnitsAdded=added==["mrjam-github-discovery.service" "mrjam-github-discovery.timer"];
    allExistingUnitTextsIdentical=lib.all (name: before.systemd.units.${name}.text==after.systemd.units.${name}.text) (builtins.attrNames before.systemd.units);
    nginxUnchanged=before.services.nginx.virtualHosts==after.services.nginx.virtualHosts && before.services.nginx.config==after.services.nginx.config;
    qualifiedPackage=toString after.services.mrjamGithubDiscovery.package=="/nix/store/adylyavm0s2y1zjrcpmg0zyklhg3p89d-mrjam-github-proposal-discovery-1";
    selectedSlotUnchanged=before.mrjamVpsApplications.activeSlot==after.mrjamVpsApplications.activeSlot;
  };
in {
  modules=baseline.modules++addition;
  evaluation={inherit checks; system=toString after.system.build.toplevel;};
  toplevel=assert lib.all (x: x) (builtins.attrValues checks); after.system.build.toplevel;
}
