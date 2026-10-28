# Pure evaluation only. The caller supplies an already approved, locked nixpkgs
# source path. These configurations are synthetic and must never be activated.
{ nixpkgs }:
let
  lib = import (nixpkgs + "/lib");
  module = ../nixos/mrjam-rust.nix;
  bluePath = "/nix/store/00000000000000000000000000000000-synthetic-mrjam-blue";
  greenPath = "/nix/store/11111111111111111111111111111111-synthetic-mrjam-green";
  evaluate = extra: import (nixpkgs + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux";
    modules = [ module {
      system.stateVersion = "26.05";
      boot.loader.grub.enable = false;
      fileSystems."/" = { device = "/dev/disk/by-label/synthetic-root"; fsType = "ext4"; };
    } extra ];
  };
  disabled = (evaluate { }).config;
  options = {
    services.mrjamRust = {
      enable = true;
      slots.blue = { enable = true; artifactStorePath = bluePath; };
      slots.green = { enable = true; artifactStorePath = greenPath; };
    };
  };
  enabled = (evaluate options).config;
  policyPasses = configuration: builtins.all (item: item.assertion)
    (builtins.filter (item: lib.hasPrefix "mrjam-rust:" item.message) configuration.assertions);
  unitBlue = enabled.systemd.services.mrjam-rust-blue;
  unitGreen = enabled.systemd.services.mrjam-rust-green;
  duplicatePorts = (evaluate (lib.recursiveUpdate options {
    services.mrjamRust.slots.green.port = 38101;
  })).config;
  noArtifact = (evaluate (lib.recursiveUpdate options {
    services.mrjamRust.slots.blue.artifactStorePath = null;
  })).config;
  derivationContext = (evaluate ({ pkgs, ... }: lib.recursiveUpdate options {
    services.mrjamRust.slots.blue.artifactStorePath = toString pkgs.hello;
  })).config;
  results = {
    disabledCreatesNoUnits = !(builtins.hasAttr "mrjam-rust-blue" disabled.systemd.services)
      && !(builtins.hasAttr "mrjam-rust-green" disabled.systemd.services);
    disabledCreatesNoIdentity = !(builtins.hasAttr "mrjam-rust-blue" disabled.users.users);
    disabledCreatesNoSlice = !(builtins.hasAttr "mrjam-rust" disabled.systemd.slices);
    enabledHasNoImplicitStarts = unitBlue.wantedBy == [ ] && unitGreen.wantedBy == [ ];
    enabledHasNoAutomaticRestart = !unitBlue.restartIfChanged && !unitGreen.restartIfChanged
      && !unitBlue.stopIfChanged && !unitGreen.stopIfChanged;
    privateDistinctListeners = unitBlue.environment.MRJAM_LISTEN_ADDR == "127.0.0.1:38101"
      && unitGreen.environment.MRJAM_LISTEN_ADDR == "127.0.0.1:38102";
    workersDisabled = unitBlue.environment.MRJAM_WORKERS_ENABLED == "false"
      && unitGreen.environment.MRJAM_WORKERS_ENABLED == "false";
    prebuiltBinaryOnly = unitBlue.serviceConfig.ExecStart == "${bluePath}/bin/mrjam-server serve"
      && unitGreen.serviceConfig.ExecStart == "${greenPath}/bin/mrjam-server serve";
    stopDoesNotForceKill = unitBlue.serviceConfig.KillSignal == "SIGTERM"
      && unitBlue.serviceConfig.TimeoutStopSec == "infinity"
      && !unitBlue.serviceConfig.SendSIGKILL;
    sharedBudget = unitBlue.serviceConfig.Slice == "mrjam-rust.slice"
      && unitGreen.serviceConfig.Slice == "mrjam-rust.slice"
      && enabled.systemd.slices.mrjam-rust.sliceConfig.CPUQuota == "100%";
    nginxUntouched = enabled.services.nginx.enable == disabled.services.nginx.enable
      && enabled.services.nginx.virtualHosts == disabled.services.nginx.virtualHosts;
    postgresqlUntouched = enabled.services.postgresql.enable == disabled.services.postgresql.enable;
    validConfigurationPasses = policyPasses enabled;
    duplicatePortsRejected = !(policyPasses duplicatePorts);
    absentArtifactRejected = !(policyPasses noArtifact);
    buildContextRejected = !(policyPasses derivationContext);
  };
in
assert builtins.all (value: value) (builtins.attrValues results);
results
