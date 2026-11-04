let
  nixpkgs=/nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source;
  pkgs=import nixpkgs {};lib=pkgs.lib;
  previous=import ./intake-discovery-host.nix;
  # Freeze the installed discovery executable while its source evolves.
  baseline=previous.modules++[{services.mrjamGithubDiscovery.package=lib.mkOverride 40
    (builtins.appendContext "/nix/store/pp91fpraqdkassx2v09qvx4kqj00pk76-mrjam-persistent-intake-discovery-1" {
      "/nix/store/4qa8r1pw1a15xb427rjhcxb4saf97vqb-mrjam-persistent-intake-discovery-1.drv"={outputs=["out"];};
    });}];
  addition=[./intake-prepare-module.nix {services.mrjamIntakePreparation.enable=true;}];
  evaluate=extra: (import (nixpkgs+"/nixos/lib/eval-config.nix") {system="x86_64-linux";modules=baseline++extra;}).config;
  before=evaluate [];after=evaluate addition;
  names=builtins.attrNames before.systemd.units;
  changed=builtins.filter (name: before.systemd.units.${name}.text!=after.systemd.units.${name}.text) names;
  added=lib.subtractLists names (builtins.attrNames after.systemd.units);
  checks={
    baselineExact=toString before.system.build.toplevel=="/nix/store/6h7c3bvc9969v2qvlxcjyjrp7cxzsq2h-nixos-system-srv1982677-26.05pre-git";
    assertionsPass=lib.all (a: a.assertion) after.assertions;
    existingUnitsUnchanged=changed==[];
    onlyPreparationAdded=added==["mrjam-intake-prepare.service" "mrjam-intake-prepare.timer"];
    routesUnchanged=before.services.nginx.virtualHosts==after.services.nginx.virtualHosts;
    greenRemainsActive=after.mrjamVpsApplications.activeSlot=="green";
    authorityUnchanged=before.services.mrjamValidationAuthority.package==after.services.mrjamValidationAuthority.package;
    discoveryUnchanged=before.services.mrjamGithubDiscovery.package==after.services.mrjamGithubDiscovery.package;
    temporaryTransportBounded=after.systemd.services.mrjam-intake-prepare.serviceConfig.TemporaryFileSystem==["/tmp:rw,size=512M,mode=1777"];
  };
in {
  modules=baseline++addition;
  evaluation={inherit checks changed added;system=toString after.system.build.toplevel;};
  toplevel=assert lib.all (x: x) (builtins.attrValues checks);after.system.build.toplevel;
}
