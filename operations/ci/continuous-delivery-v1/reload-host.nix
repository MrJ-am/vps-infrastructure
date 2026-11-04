# Preserve every application and route; prepare native NixOS graceful reloads.
let
  nixpkgs=/nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source;
  lib=(import nixpkgs {}).lib;
  baseline=import ./discovery-host.nix;
  addition=[{ services.nginx.enableReload=true; }];
  evaluate=extra: (import (nixpkgs+"/nixos/lib/eval-config.nix") {
    system="x86_64-linux"; modules=baseline.modules++extra;
  }).config;
  before=evaluate []; after=evaluate addition;
  names=builtins.attrNames before.systemd.units;
  changed=builtins.filter (name: before.systemd.units.${name}.text != after.systemd.units.${name}.text) names;
  added=lib.subtractLists names (builtins.attrNames after.systemd.units);
  etcChanged=builtins.filter (name: before.environment.etc.${name}!=after.environment.etc.${name}) (builtins.attrNames before.environment.etc);
  etcAdded=lib.subtractLists (builtins.attrNames before.environment.etc) (builtins.attrNames after.environment.etc);
  checks={
    baselineExact=toString before.system.build.toplevel=="/nix/store/q7s20jjy4b0czv3kj1kmzi15r7inr94f-nixos-system-srv1982677-26.05pre-git";
    assertionsPass=lib.all (a: a.assertion) after.assertions;
    onlyNginxUnitChanged=changed==["nginx.service"];
    onlyReloadUnitAdded=added==["nginx-config-reload.service"];
    routesIdentical=before.services.nginx.virtualHosts==after.services.nginx.virtualHosts;
    selectedSlotUnchanged=before.mrjamVpsApplications.activeSlot==after.mrjamVpsApplications.activeSlot;
    allOtherEtcIdentical=etcChanged==["systemd/system"];
    onlyNginxConfigurationAdded=etcAdded==["nginx/nginx.conf"];
    reloadEnabled=after.services.nginx.enableReload;
  };
in {
  modules=baseline.modules++addition;
  evaluation={inherit checks changed added etcChanged etcAdded; system=toString after.system.build.toplevel;};
  toplevel=assert lib.all (x: x) (builtins.attrValues checks); after.system.build.toplevel;
}
