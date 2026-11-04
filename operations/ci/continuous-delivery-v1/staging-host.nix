let
  nixpkgs=/nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source;
  pkgs=import nixpkgs {};lib=pkgs.lib;
  base=import ./acceptance-host.nix;
  installed=import ./preparation-host.nix;
  packages={
    preparation=builtins.storePath /nix/store/vcr44i9bril5lr7nbf8ci8amgf57a969-mrjam-delivery-preparation-1;
    acceptance=builtins.storePath /nix/store/vkvzk7vd6w5jawhda3vz7p88d5wpdqm0-mrjam-separated-acceptance-services-1;
    staging=builtins.storePath /nix/store/zk671bry18xn1ahfhjy8y2yg31mpli23-mrjam-protected-staging-service-1;
  };
  control=lib.mapAttrs (_: p: builtins.unsafeDiscardStringContext (toString p)) packages;
  modules=base.modules++[(import ./delivery-control-plane.nix {inherit control;})];
  evaluate=mods: (import (nixpkgs+"/nixos/lib/eval-config.nix") {system="x86_64-linux";modules=mods;}).config;
  before=evaluate installed.modules;after=evaluate modules;
  names=builtins.attrNames before.systemd.units;
  added=lib.subtractLists names (builtins.attrNames after.systemd.units);
  changed=builtins.filter (n: before.systemd.units.${n}.text!=after.systemd.units.${n}.text) names;
  allowed=["mrjam-delivery-preparation.service"]++map (s: "mrjam-acceptance-${s}.service") ["mirror" "review" "merge" "sync"];
  unit=after.systemd.services.mrjam-delivery-staging.serviceConfig;
  checks={
    baselineExact=toString before.system.build.toplevel=="/nix/store/m01vhv8qwbaqs41ns64gkih8zwgvsbvw-nixos-system-srv1982677-26.05pre-git";
    assertionsPass=lib.all (a: a.assertion) after.assertions;
    onlyStagingAdded=added==["mrjam-delivery-staging.service" "mrjam-delivery-staging.timer"];
    onlyControllersChanged=lib.all (n: builtins.elem n allowed) changed;
    routesUnchanged=before.services.nginx.virtualHosts==after.services.nginx.virtualHosts;
    adoptedUnchanged=before.environment.etc."mrjam-delivery-adopted.json".source==after.environment.etc."mrjam-delivery-adopted.json".source;
    observerOnly=unit.LoadCredential==["forgejo-observer:/var/lib/mrjam-ci-credentials/forgejo-policy-token"];
    boundedResources=unit.MemoryMax=="768M" && unit.CPUQuota=="50%" && unit.TasksMax==128;
    stagerSurvivesActivation= !after.systemd.services.mrjam-delivery-staging.restartIfChanged
      && !after.systemd.services.mrjam-delivery-staging.stopIfChanged;
  };
  state={
    schema_version=1;system=toString after.system.build.toplevel;
    active_slot=after.mrjamVpsApplications.activeSlot;control_plane=control;
    adopted=toString after.environment.etc."mrjam-delivery-adopted.json".source;
    slots=lib.genAttrs ["blue" "green"] (slot: {
      server=after.services.mrjamRust.slots.${slot}.artifactStorePath;
      runtime=after.mrjamVpsApplications.slots.${slot};
    });
  };
in {
  inherit modules;
  evaluation={inherit checks changed added state;packages=control;system=state.system;};
  toplevel=assert lib.all (x: x) (builtins.attrValues checks);after.system.build.toplevel;
}
