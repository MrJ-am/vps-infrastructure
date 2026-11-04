let
  nixpkgs=/nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source;
  pkgs=import nixpkgs {};lib=pkgs.lib;
  baseline=import ./promotion-service-host.nix;
  package=builtins.appendContext "/nix/store/1aj8c8s3q34dj5cf7x7gcw1grbk36im8-mrjam-protected-promotion-service-1" {
    "/nix/store/r0r8wdhrpsvjv5mirfaqcnv93m3pyff0-mrjam-protected-promotion-service-1.drv"={outputs=["out"];};
  };
  addition=[{systemd.services.mrjam-promotion.serviceConfig.ExecStart=lib.mkOverride 10 "${package}/bin/mrjam-promotion";}];
  evaluate=extra: (import (nixpkgs+"/nixos/lib/eval-config.nix") {system="x86_64-linux";modules=baseline.modules++extra;}).config;
  before=evaluate [];after=evaluate addition;names=builtins.attrNames before.systemd.units;
  changed=builtins.filter (name: before.systemd.units.${name}.text!=after.systemd.units.${name}.text) names;
  checks={
    baselineExact=toString before.system.build.toplevel=="/nix/store/wjx28fxryilx9hq6szckhqn871jbf4zb-nixos-system-srv1982677-26.05pre-git";
    assertionsPass=lib.all (a: a.assertion) after.assertions;
    onlyRecoveryServiceChanges=changed==["mrjam-promotion.service"];
    noUnitsAdded=names==builtins.attrNames after.systemd.units;
    routesUnchanged=before.services.nginx.virtualHosts==after.services.nginx.virtualHosts;
    adoptedUnchanged=before.environment.etc."mrjam-delivery-adopted.json".source==after.environment.etc."mrjam-delivery-adopted.json".source;
  };
in {
  modules=baseline.modules++addition;
  evaluation={inherit checks changed;system=toString after.system.build.toplevel;package=toString package;};
  toplevel=assert lib.all (x: x) (builtins.attrValues checks);after.system.build.toplevel;
}
