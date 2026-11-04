# Change only the read-only GitHub discovery unit's protected executable.
let
  nixpkgs=/nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source;
  pkgs=import nixpkgs {};lib=pkgs.lib;
  baseline=import ./delivery-promoted-host.nix;
  addition={services.mrjamGithubDiscovery.package=lib.mkForce (import ./intake-discovery.nix {inherit pkgs;});};
  evaluate=extra: (import (nixpkgs+"/nixos/lib/eval-config.nix") {system="x86_64-linux";modules=baseline.modules++extra;}).config;
  before=evaluate [];after=evaluate [addition];
  names=builtins.attrNames before.systemd.units;
  changed=builtins.filter (name: before.systemd.units.${name}.text!=after.systemd.units.${name}.text) names;
  checks={
    baselineExact=toString before.system.build.toplevel=="/nix/store/xrh880q8hiv7c4v7cng5mi1vg4j6p264-nixos-system-srv1982677-26.05pre-git";
    assertionsPass=lib.all (a: a.assertion) after.assertions;
    onlyDiscoveryChanged=changed==["mrjam-github-discovery.service"];
    noUnitsAdded=names==builtins.attrNames after.systemd.units;
    routesUnchanged=before.services.nginx.virtualHosts==after.services.nginx.virtualHosts;
    greenRemainsActive=after.mrjamVpsApplications.activeSlot=="green";
    authorityUnchanged=before.services.mrjamValidationAuthority.package==after.services.mrjamValidationAuthority.package;
    timersUnchanged=builtins.attrNames before.systemd.timers==builtins.attrNames after.systemd.timers
      && lib.all (name: before.systemd.units.${name+".timer"}.text==after.systemd.units.${name+".timer"}.text) (builtins.attrNames before.systemd.timers);
  };
in {
  modules=baseline.modules++[addition];
  evaluation={inherit checks changed;system=toString after.system.build.toplevel;};
  toplevel=assert lib.all (x: x) (builtins.attrValues checks);after.system.build.toplevel;
}
