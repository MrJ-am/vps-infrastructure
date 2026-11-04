# Evaluation-only invented paths: never build or activate this configuration.
let
  nixpkgs = /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source;
  lib = (import nixpkgs {}).lib;
  baseline = import ../../vise/requalification-20261103/promoted.nix;
  evaluate = modules: (import (nixpkgs + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux"; modules = baseline.modules ++ modules;
  }).config;
  before = evaluate [];
  server = "/nix/store/11111111111111111111111111111111-synthetic-server-not-installed";
  runtime = "/nix/store/22222222222222222222222222222222-synthetic-runtime-not-installed";
  replacement = import ./slot-artifacts.nix {
    slot = "green"; serverStorePath = server; runtimeStorePath = runtime;
  };
  after = evaluate [replacement];
  unit = cfg: name: cfg.systemd.units."${name}.service".text;
  rejects = args: !(builtins.tryEval ((import ./slot-artifacts.nix args) {
    inherit lib; config = {};
  })).success;
  checks = {
    baselineExact = toString before.system.build.toplevel == "/nix/store/17lw8y05pgzmcl9q6wvknbf7z1znajl9-nixos-system-srv1982677-26.05pre-git";
    assertionsPass = lib.all (a: a.assertion) after.assertions;
    activeUnitIdentical = unit before "mrjam-rust-blue" == unit after "mrjam-rust-blue";
    newInactiveExecutable = after.systemd.services.mrjam-rust-green.serviceConfig.ExecStart == "${server}/bin/mrjam-server serve --config ${runtime}/runtime.json";
    inactiveUnitChanged = unit before "mrjam-rust-green" != unit after "mrjam-rust-green";
    routeIdentical = before.services.nginx.config == after.services.nginx.config
      && before.services.nginx.virtualHosts == after.services.nginx.virtualHosts;
    activeSlotIdentical = before.mrjamVpsApplications.activeSlot == after.mrjamVpsApplications.activeSlot;
    noImplicitRestart = !after.systemd.services.mrjam-rust-green.restartIfChanged
      && !after.systemd.services.mrjam-rust-green.stopIfChanged;
    bootPolicyIdentical = before.systemd.services.mrjam-rust-green.wantedBy == after.systemd.services.mrjam-rust-green.wantedBy;
    retainedUnitsIdentical = lib.all (name: unit before name == unit after name)
      [ "postgresql" "nginx" "vise" "forgejo" ];
    unknownSlotRefused = rejects { slot = "red"; serverStorePath = server; runtimeStorePath = runtime; };
    nonStorePathRefused = rejects { slot = "green"; serverStorePath = "/tmp/candidate"; runtimeStorePath = runtime; };
    buildContextRefused = rejects { slot = "green";
      serverStorePath = builtins.toFile "synthetic-context" "not-an-artifact"; runtimeStorePath = runtime; };
  };
in assert lib.all (x: x) (builtins.attrValues checks);
{ inherit checks; scope = "nixos-evaluation-only-no-runtime-validation-or-activation"; }
