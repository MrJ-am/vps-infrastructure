# Bootstrap the permanent preparation service, preserving all application state.
let
  nixpkgs=/nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source;
  pkgs=import nixpkgs {};lib=pkgs.lib;
  baseline=import ./acceptance-host.nix;
  # Qualified bootstrap package: future source edits must not rewrite this baseline.
  package=builtins.storePath "/nix/store/rrwc9pz5pcs3j22qzjsn4rvb6r28ggr4-mrjam-delivery-preparation-1";
  control={
    preparation=builtins.unsafeDiscardStringContext (toString package);
    acceptance="/nix/store/5krkhb1chsm97vvcvjra0zbbqnikypc4-mrjam-separated-acceptance-services-1";
  };
  addition=[(import ./delivery-control-plane.nix {inherit control;})];
  evaluate=extra: (import (nixpkgs+"/nixos/lib/eval-config.nix") {system="x86_64-linux";modules=baseline.modules++extra;}).config;
  before=evaluate [];after=evaluate addition;
  names=builtins.attrNames before.systemd.units;
  added=lib.subtractLists names (builtins.attrNames after.systemd.units);
  changed=builtins.filter (name: before.systemd.units.${name}.text!=after.systemd.units.${name}.text) names;
  unit=after.systemd.services.mrjam-delivery-preparation.serviceConfig;
  checks={
    baselineExact=toString before.system.build.toplevel=="/nix/store/y9ddjv4pfncss1gjnd4msfywfxr7s8b4-nixos-system-srv1982677-26.05pre-git";
    assertionsPass=lib.all (a: a.assertion) after.assertions;
    onlyPreparationAdded=added==["mrjam-delivery-preparation.service" "mrjam-delivery-preparation.timer"];
    existingUnitsUnchanged=changed==[];
    routesUnchanged=before.services.nginx.virtualHosts==after.services.nginx.virtualHosts;
    adoptionUnchanged=before.environment.etc."mrjam-delivery-adopted.json".source==after.environment.etc."mrjam-delivery-adopted.json".source;
    observerOnly=unit.LoadCredential==["forgejo-observer:/var/lib/mrjam-ci-credentials/forgejo-policy-token"];
    boundedResources=unit.MemoryMax=="3G" && unit.CPUQuota=="50%" && unit.TasksMax==128;
    stateOnlyWritable=unit.ProtectSystem=="strict" && !(unit ? ReadWritePaths);
    activationAndSignerMasked=lib.all (p: builtins.elem p unit.InaccessiblePaths)
      ["-/run/systemd/private" "-/run/dbus/system_bus_socket" "-/run/mrjam-validation-authority"];
  };
  state={
    schema_version=1;system=toString after.system.build.toplevel;
    active_slot=after.mrjamVpsApplications.activeSlot;
    adopted=toString after.environment.etc."mrjam-delivery-adopted.json".source;
    control_plane=control;
    slots=lib.genAttrs ["blue" "green"] (slot: {
      server=after.services.mrjamRust.slots.${slot}.artifactStorePath;
      runtime=after.mrjamVpsApplications.slots.${slot};
    });
  };
in {
  modules=baseline.modules++addition;
  evaluation={inherit checks added changed state;system=state.system;package=toString package;};
  toplevel=assert lib.all (x: x) (builtins.attrValues checks);after.system.build.toplevel;
}
