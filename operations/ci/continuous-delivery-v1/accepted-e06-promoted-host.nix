# Atomic system-generation binding: public routing, boot slot and adopted source.
# Controller updates the durable job under the same adoption lock.
let
  nixpkgs=/nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source;
  pkgs=import nixpkgs {};lib=pkgs.lib;
  staged=import ./promotion-runtime-host.nix;
  promotion={
    mrjamVpsApplications.activeSlot=lib.mkOverride 40 "blue";
    systemd.services.mrjam-rust-blue.wantedBy=lib.mkOverride 40 ["multi-user.target"];
    systemd.services.mrjam-rust-green.wantedBy=lib.mkOverride 40 [];
    services.mrjamIntakePreparation.adopted=lib.mkForce (import ./accepted-e06-adopted.nix {inherit pkgs;});
  };
  evaluate=extra: (import (nixpkgs+"/nixos/lib/eval-config.nix") {system="x86_64-linux";modules=staged.modules++extra;}).config;
  before=evaluate [];after=evaluate [promotion];
  names=builtins.attrNames before.systemd.units;
  changed=builtins.filter (name: before.systemd.units.${name}.text!=after.systemd.units.${name}.text) names;
  checks={
    stagedExact=toString before.system.build.toplevel=="/nix/store/xs2q4rwk8bhr78y7l1xqkzl60244312k-nixos-system-srv1982677-26.05pre-git";
    assertionsPass=lib.all (a: a.assertion) after.assertions;
    noUnitsAdded=names==builtins.attrNames after.systemd.units;
    onlyRoutingAndBootUnits=lib.all (name: builtins.elem name ["nginx.service" "nginx-config-reload.service" "mrjam-rust-blue.service" "mrjam-rust-green.service"]) changed;
    blueCommandIdentical=before.systemd.services.mrjam-rust-blue.serviceConfig==after.systemd.services.mrjam-rust-blue.serviceConfig;
    greenCommandIdentical=before.systemd.services.mrjam-rust-green.serviceConfig==after.systemd.services.mrjam-rust-green.serviceConfig;
    noImplicitRestart= !after.systemd.services.mrjam-rust-blue.restartIfChanged && !after.systemd.services.mrjam-rust-blue.stopIfChanged
      && !after.systemd.services.mrjam-rust-green.restartIfChanged && !after.systemd.services.mrjam-rust-green.stopIfChanged && !after.systemd.services.nginx.restartIfChanged;
    nativeReload=after.services.nginx.enableReload;
    blueBoot=after.systemd.services.mrjam-rust-blue.wantedBy==["multi-user.target"];
    greenNoBoot=after.systemd.services.mrjam-rust-green.wantedBy==[];
    authorityUnchanged=before.services.mrjamValidationAuthority.package==after.services.mrjamValidationAuthority.package;
    controllerUnchanged=before.systemd.services.mrjam-admission-controller.serviceConfig==after.systemd.services.mrjam-admission-controller.serviceConfig;
  };
in {
  modules=staged.modules++[promotion];
  evaluation={inherit checks changed;system=toString after.system.build.toplevel;};
  toplevel=assert lib.all (x: x) (builtins.attrValues checks);after.system.build.toplevel;
}
