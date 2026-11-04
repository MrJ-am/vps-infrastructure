let
  nixpkgs=/nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source;
  pkgs=import nixpkgs {};lib=pkgs.lib;
  baseline=import ./accepted-e06-staged-host.nix;
  # Installed, qualified controller. Keep this historical baseline fixed while
  # later controller recipes are developed.
  controller=builtins.appendContext "/nix/store/qmzbv6zskr9qzhh3ifqs010jz26q2jlh-mrjam-protected-admission-controller-1" {
    "/nix/store/yn3ipb5m7idihv9dn9q324hap90rhh5g-mrjam-protected-admission-controller-1.drv"={outputs=["out"];};
  };
  addition=[{services.mrjamAdmissionController.package=lib.mkOverride 10 controller;}];
  evaluate=extra: (import (nixpkgs+"/nixos/lib/eval-config.nix") {
    system="x86_64-linux";modules=baseline.modules++extra;
  }).config;
  before=evaluate [];after=evaluate addition;
  names=builtins.attrNames before.systemd.units;
  changed=builtins.filter (name: before.systemd.units.${name}.text!=after.systemd.units.${name}.text) names;
  checks={
    baselineExact=toString before.system.build.toplevel=="/nix/store/iiac77hsa8mrlcf87n7jripg7vdic77x-nixos-system-srv1982677-26.05pre-git";
    assertionsPass=lib.all (a: a.assertion) after.assertions;
    onlyControllerChanged=changed==["mrjam-admission-controller.service"];
    noUnitsAdded=names==builtins.attrNames after.systemd.units;
    routesUnchanged=before.services.nginx.virtualHosts==after.services.nginx.virtualHosts;
    adoptedUnchanged=before.environment.etc."mrjam-delivery-adopted.json".source==after.environment.etc."mrjam-delivery-adopted.json".source;
    runnerUnchanged=before.systemd.services.mrjam-forgejo-runner.serviceConfig==after.systemd.services.mrjam-forgejo-runner.serviceConfig;
    authorityUnchanged=before.services.mrjamValidationAuthority.package==after.services.mrjamValidationAuthority.package;
  };
in {
  modules=baseline.modules++addition;
  evaluation={inherit checks changed;system=toString after.system.build.toplevel;controller=toString controller;};
  toplevel=assert lib.all (x: x) (builtins.attrValues checks);after.system.build.toplevel;
}
