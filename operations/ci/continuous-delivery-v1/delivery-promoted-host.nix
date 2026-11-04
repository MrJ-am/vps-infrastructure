# Trusted route/boot transition; never imports candidate Nix.
let
  nixpkgs=/nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source;
  lib=(import nixpkgs {}).lib;
  staged=import ./delivery-staged-host.nix;
  promotion={
    mrjamVpsApplications.activeSlot=lib.mkForce "green";
    systemd.services.mrjam-rust-blue.wantedBy=lib.mkForce [];
    systemd.services.mrjam-rust-green.wantedBy=lib.mkForce ["multi-user.target"];
  };
  evaluate=extra: (import (nixpkgs+"/nixos/lib/eval-config.nix") {system="x86_64-linux";modules=staged.modules++extra;}).config;
  before=evaluate [];after=evaluate [promotion];
  names=builtins.attrNames before.systemd.units;
  changed=builtins.filter (name: before.systemd.units.${name}.text!=after.systemd.units.${name}.text) names;
  checks={
    stagedExact=toString before.system.build.toplevel=="/nix/store/z3rr0v83aar7xnghm96840cwfr1hjdiv-nixos-system-srv1982677-26.05pre-git";
    assertionsPass=lib.all (a: a.assertion) after.assertions;
    noUnitsAdded=names==builtins.attrNames after.systemd.units;
    onlyRoutingAndBoot=lib.all (name: builtins.elem name ["nginx.service" "nginx-config-reload.service" "mrjam-rust-blue.service" "mrjam-rust-green.service"]) changed;
    blueCommandIdentical=before.systemd.services.mrjam-rust-blue.serviceConfig==after.systemd.services.mrjam-rust-blue.serviceConfig;
    greenCommandIdentical=before.systemd.services.mrjam-rust-green.serviceConfig==after.systemd.services.mrjam-rust-green.serviceConfig;
    noImplicitRestart= !after.systemd.services.mrjam-rust-blue.restartIfChanged && !after.systemd.services.mrjam-rust-blue.stopIfChanged && !after.systemd.services.mrjam-rust-green.restartIfChanged && !after.systemd.services.mrjam-rust-green.stopIfChanged && !after.systemd.services.nginx.restartIfChanged;
    nativeReload=after.services.nginx.enableReload;
    greenBoot=after.systemd.services.mrjam-rust-green.wantedBy==["multi-user.target"];
    blueNoBoot=after.systemd.services.mrjam-rust-blue.wantedBy==[];
  };
in {
  modules=staged.modules++[promotion];
  evaluation={inherit checks changed;system=toString after.system.build.toplevel;};
  toplevel=assert lib.all (x: x) (builtins.attrValues checks);after.system.build.toplevel;
}
