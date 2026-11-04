# Evaluation only with locally validated artifacts, not production authority.
let
  nixpkgs=/nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source;
  lib=(import nixpkgs {}).lib;
  baseline=import ./admission-host.nix;
  server=import ./delivery-server-qualification.nix;
  runtime=import ./delivery-complete-runtime-qualification.nix;
  replacement=import ./slot-artifacts.nix {
    slot="green";
    serverStorePath=builtins.unsafeDiscardStringContext (toString server);
    runtimeStorePath=builtins.unsafeDiscardStringContext (toString runtime);
  };
  evaluate=extra: (import (nixpkgs+"/nixos/lib/eval-config.nix") {
    system="x86_64-linux";modules=baseline.modules++extra;
  }).config;
  before=evaluate [];after=evaluate [replacement];
  names=builtins.attrNames before.systemd.units;
  changed=builtins.filter (name: before.systemd.units.${name}.text!=after.systemd.units.${name}.text) names;
  checks={
    baselineExact=toString before.system.build.toplevel=="/nix/store/frha1lc5vwqx4d5bzs6p2hfabk8r6r49-nixos-system-srv1982677-26.05pre-git";
    assertionsPass=lib.all (a: a.assertion) after.assertions;
    onlyInactiveUnitChanges=changed==["mrjam-rust-green.service"];
    noUnitAdded=names==builtins.attrNames after.systemd.units;
    activeSlotStillBlue=before.mrjamVpsApplications.activeSlot=="blue" && after.mrjamVpsApplications.activeSlot=="blue";
    routesUnchanged=before.services.nginx.virtualHosts==after.services.nginx.virtualHosts;
    noImplicitRestart= !after.systemd.services.mrjam-rust-green.restartIfChanged && !after.systemd.services.mrjam-rust-green.stopIfChanged;
    bootPolicyUnchanged=before.systemd.services.mrjam-rust-green.wantedBy==after.systemd.services.mrjam-rust-green.wantedBy;
  };
in assert lib.all (x: x) (builtins.attrValues checks);
{inherit checks changed;scope="local-artifacts-inactive-slot-evaluation-only";production_activation=false;}
