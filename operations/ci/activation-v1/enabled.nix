# Enable the server feature after separately installing the isolated services.
# Service starts remain explicit until the real end-to-end acceptance succeeds.
{ controllerRevision }:
let
  nixpkgs = /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source;
  pkgs = import nixpkgs { system = "x86_64-linux"; };
  lib = pkgs.lib;
  oldArgs = (import ../host-candidate-v1/evaluation-v3.nix {
    controllerRevision = "e1dc4a31dc5a8ff37ab0639fb1af131e40263e4e";
  }).evaluation.arguments;
  args = oldArgs // { inherit controllerRevision; enableBoundedActions = true; };
  eval = arguments: (import (nixpkgs + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux";
    modules = [ ../../hosts/mrjam-vps/candidate-unicast.nix
      (import ../host-profile-authority-report-v3.nix arguments) ];
  }).config;
  old = eval oldArgs;
  current = eval args;
  names = builtins.attrNames old.systemd.units;
  changed = lib.filter (n: old.systemd.units.${n}.text != current.systemd.units.${n}.text) names;
  checks = {
    baselineExact = toString old.system.build.toplevel == "/nix/store/g1l3zif8rwndmdcyc1vylwasaxds9iia-nixos-system-srv1982677-26.05pre-git";
    assertionsPass = lib.all (a: a.assertion) current.assertions;
    sameUnits = names == builtins.attrNames current.systemd.units;
    onlyForgejoUnitChanges = changed == [ "forgejo.service" ];
    onlyActionsSettingChanges = (old.services.mrjamForgejoHost.settings // {
      actions = old.services.mrjamForgejoHost.settings.actions // { ENABLED = true; };
    }) == current.services.mrjamForgejoHost.settings;
    signingPackageUnchanged = toString old.services.mrjamValidationAuthority.package == toString current.services.mrjamValidationAuthority.package;
    policyPlanOnly = current.services.mrjamForgejoPolicy.mode == "plan";
    noImplicitRunnerStart = current.systemd.services.mrjam-forgejo-runner.wantedBy == [];
  };
in {
  evaluation = { inherit checks changed controllerRevision; candidate = toString current.system.build.toplevel; };
  toplevel = assert lib.all (x: x) (builtins.attrValues checks); current.system.build.toplevel;
}
