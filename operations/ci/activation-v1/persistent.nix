# Boot wiring for the already qualified, repository-scoped validation chain.
let
  nixpkgs = /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source;
  pkgs = import nixpkgs { system = "x86_64-linux"; };
  lib = pkgs.lib;
  args = (import ../host-candidate-v1/evaluation-v3.nix {
    controllerRevision = "95f90ec9d3acdcd260f25b2dca88a8a55574bf11";
  }).evaluation.arguments // { enableBoundedActions = true; };
  sockets = [ "mrjam-validation-worker" "mrjam-validation-collector" "mrjam-validation-export" "mrjam-validation-authority" ];
  wiring = {
    systemd.sockets = lib.genAttrs sockets (_: { wantedBy = [ "sockets.target" ]; });
    systemd.services.mrjam-validation-staging.serviceConfig.RemainAfterExit = true;
    systemd.services.mrjam-forgejo-runner = {
      wantedBy = [ "multi-user.target" ];
      after = [ "forgejo.service" "mrjam-validation-staging.service" ] ++ map (n: n + ".socket") sockets;
      requires = [ "forgejo.service" "mrjam-validation-staging.service" ] ++ map (n: n + ".socket") sockets;
    };
  };
  eval = extra: (import (nixpkgs + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux";
    modules = [ ../../hosts/mrjam-vps/candidate-unicast.nix (import ../host-profile-authority-report-v3.nix args) ] ++ extra;
  }).config;
  old = eval []; current = eval [wiring];
  changed = lib.filter (n: old.systemd.units.${n}.text != current.systemd.units.${n}.text) (builtins.attrNames old.systemd.units);
  checks = {
    baselineExact = toString old.system.build.toplevel == "/nix/store/i367qqkm6fzsr9rh8lbs2ymf53166hj9-nixos-system-srv1982677-26.05pre-git";
    assertionsPass = lib.all (a: a.assertion) current.assertions;
    onlyBootWiringChanges = changed == [ "mrjam-forgejo-runner.service" "mrjam-validation-authority.socket" "mrjam-validation-collector.socket" "mrjam-validation-export.socket" "mrjam-validation-staging.service" "mrjam-validation-worker.socket" ];
    noAutomaticRegistration = current.systemd.services.mrjam-forgejo-registration.wantedBy == [];
    noAutomaticSchemaUpgrade = current.systemd.services.mrjam-upgrade-forgejo-schema.wantedBy == [];
    policyUnchanged = old.services.mrjamForgejoPolicy == current.services.mrjamForgejoPolicy;
  };
in {
  modules = [ ../../hosts/mrjam-vps/candidate-unicast.nix (import ../host-profile-authority-report-v3.nix args) wiring ];
  evaluation = { inherit checks changed; candidate = toString current.system.build.toplevel; };
  toplevel = assert lib.all (x: x) (builtins.attrValues checks); current.system.build.toplevel;
}
