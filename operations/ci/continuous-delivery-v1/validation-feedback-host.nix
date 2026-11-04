let
  nixpkgs=/nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source;
  pkgs=import nixpkgs {};lib=pkgs.lib;
  previous=import ./runner-policy-directory-host.nix;
  baseline=previous.modules++[{
    services.mrjamAdmissionController.package=lib.mkOverride 40
      (builtins.appendContext "/nix/store/kypw185n5fsch7lynnriirc311md7ajj-mrjam-protected-admission-controller-1" {
        "/nix/store/mbwvml6flhfmq7xxk3iviyrjyncrknxi-mrjam-protected-admission-controller-1.drv"={outputs=["out"];};
      });
  }];
  addition=[{services.mrjamAdmissionController.package=lib.mkOverride 30
    (import ./admission-controller.nix {inherit pkgs;});}];
  evaluate=extra: (import (nixpkgs+"/nixos/lib/eval-config.nix") {
    system="x86_64-linux";modules=baseline++extra;
  }).config;
  before=evaluate [];after=evaluate addition;
  names=builtins.attrNames before.systemd.units;
  changed=builtins.filter (name: before.systemd.units.${name}.text!=after.systemd.units.${name}.text) names;
  checks={
    baselineExact=toString before.system.build.toplevel=="/nix/store/zsfxxknh53v8s20v98m2b6ra9inl6471-nixos-system-srv1982677-26.05pre-git";
    onlyControllerChanged=changed==["mrjam-admission-controller.service"];
    unitsUnchanged=names==builtins.attrNames after.systemd.units;
    assertionsPass=lib.all (a: a.assertion) after.assertions;
    routesUnchanged=before.services.nginx.virtualHosts==after.services.nginx.virtualHosts;
    authorityUnchanged=before.services.mrjamValidationAuthority.package==after.services.mrjamValidationAuthority.package;
    runnerUnchanged=before.systemd.services.mrjam-forgejo-runner.serviceConfig==after.systemd.services.mrjam-forgejo-runner.serviceConfig;
  };
in {
  modules=baseline++addition;
  evaluation={inherit checks changed;system=toString after.system.build.toplevel;};
  toplevel=assert lib.all (x: x) (builtins.attrValues checks);after.system.build.toplevel;
}
