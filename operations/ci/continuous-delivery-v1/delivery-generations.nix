# Trusted baseline + data-only current state + independently bound candidate.
# No module/expression is ever taken from a proposal or a JSON field.
{ stateFile, candidatePath }:
let
  nixpkgs=/nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source;
  lib=(import nixpkgs {}).lib;
  baselineRecipe=builtins.storePath "/nix/store/dnir95r62s6xi57dcygv80fqhirkhzas-mrjam-protected-delivery-recipe-1";
  baseline=import (baselineRecipe+"/operations/ci/continuous-delivery-v1/acceptance-host.nix");
  state=builtins.fromJSON (builtins.unsafeDiscardStringContext (builtins.readFile stateFile));
  candidate=builtins.fromJSON (builtins.unsafeDiscardStringContext
    (builtins.readFile (builtins.storePath candidatePath+"/descriptor.json")));
  bundle=builtins.fromJSON (builtins.unsafeDiscardStringContext
    (builtins.readFile (builtins.storePath candidate.bundle+"/descriptor.json")));
  slots=["blue" "green"];
  store=value: builtins.isString value && builtins.match "/nix/store/[0-9abcdfghijklmnpqrsvwxyz]{32}-[A-Za-z0-9+._-]+" value!=null;
  controlPlane=lib.optional (state ? control_plane)
    (import ./delivery-control-plane.nix {control=state.control_plane;});
  evaluate=extra: (import (nixpkgs+"/nixos/lib/eval-config.nix") {
    system="x86_64-linux";modules=baseline.modules++controlPlane++[./delivery-vise-backup-baseline.nix]++extra;
  }).config;
  base=evaluate [];
  baseSlots=lib.genAttrs slots (slot: {
    server=base.services.mrjamRust.slots.${slot}.artifactStorePath;
    runtime=base.mrjamVpsApplications.slots.${slot};
  });
  overlay=s: {
    services.mrjamVise.artifactRoot=lib.mkIf (s ? vise) (lib.mkOverride (-10) s.vise.artifact);
    environment.etc=lib.optionalAttrs (s ? vise) {
      "mrjam-vise-delivery-adopted.json".source=builtins.storePath s.vise.adopted;
    };
    mrjamVpsApplications.activeSlot=lib.mkOverride (-10) s.active_slot;
    mrjamVpsApplications.slots=lib.genAttrs slots (slot:
      lib.mkIf (s.slots.${slot}.runtime!=baseSlots.${slot}.runtime) (lib.mkOverride (-10) s.slots.${slot}.runtime));
    services.mrjamRust.slots=lib.genAttrs slots (slot: {
      artifactStorePath=lib.mkIf (s.slots.${slot}.server!=baseSlots.${slot}.server) (lib.mkOverride (-10) s.slots.${slot}.server);
    });
    services.mrjamIntakePreparation.adopted=lib.mkIf
      (s.adopted!=toString base.services.mrjamIntakePreparation.adopted)
      (lib.mkOverride (-10) (builtins.storePath s.adopted));
    systemd.services=lib.genAttrs (map (slot: "mrjam-rust-${slot}") slots) (name: {
      wantedBy=lib.mkOverride (-10) (lib.optional (name=="mrjam-rust-${s.active_slot}") "multi-user.target");
    });
    # Match NixOS list merging when the ViSe module follows the platform one:
    # its dependency precedes those of the earlier platform module.
    system.extraDependencies=lib.optional (s ? vise) (builtins.storePath s.vise.artifact)
      ++lib.concatMap (slot: lib.concatMap (field:
      lib.optional (s.slots.${slot}.${field}!=baseSlots.${slot}.${field})
        (builtins.storePath s.slots.${slot}.${field})) ["server" "runtime"]) slots;
  };
  off=if state.active_slot=="blue" then "green" else "blue";
  stagedState=state // {slots=state.slots // {${off}={inherit (bundle) server runtime;};};};
  promotedState=stagedState // {active_slot=off;adopted=candidate.adopted;};
  before=evaluate [(overlay state)];staged=evaluate [(overlay stagedState)];promoted=evaluate [(overlay promotedState)];
  names=builtins.attrNames before.systemd.units;
  changed=config: builtins.filter (name: before.systemd.units.${name}.text!=config.systemd.units.${name}.text) names;
  runtime=path: builtins.fromJSON (builtins.unsafeDiscardStringContext (builtins.readFile (builtins.storePath path+"/runtime.json")));
  oldRuntime=runtime state.slots.${off}.runtime;newRuntime=runtime bundle.runtime;
  checks={
    currentExact=toString before.system.build.toplevel==state.system;
    assertionsPass=lib.all (c: lib.all (a: a.assertion) c.assertions) [before staged promoted];
    stageChangesOnlyOffTraffic=lib.all (n: n=="mrjam-rust-${off}.service") (changed staged);
    unitsPreserved=lib.all (c: names==builtins.attrNames c.systemd.units) [staged promoted];
    stagedRoutesUnchanged=before.services.nginx.virtualHosts==staged.services.nginx.virtualHosts;
    stagedAdoptionUnchanged=before.environment.etc."mrjam-delivery-adopted.json".source==staged.environment.etc."mrjam-delivery-adopted.json".source;
    nonAssetConfigurationUnchanged=builtins.removeAttrs oldRuntime ["assets"]==builtins.removeAttrs newRuntime ["assets"];
    assetRoutingUnchanged=map (a: builtins.removeAttrs a ["directory" "manifest_sha256"]) oldRuntime.assets
      ==map (a: builtins.removeAttrs a ["directory" "manifest_sha256"]) newRuntime.assets;
    promotionChangesOnlyRoutesAndBoot=lib.all (n: builtins.elem n
      ["nginx.service" "nginx-config-reload.service" "mrjam-rust-blue.service" "mrjam-rust-green.service"]) (changed promoted);
    promotionRetainsCommands=lib.all (slot: staged.systemd.services."mrjam-rust-${slot}".serviceConfig
      ==promoted.systemd.services."mrjam-rust-${slot}".serviceConfig) slots;
    noImplicitRestart=lib.all (c: lib.all (slot: !c.systemd.services."mrjam-rust-${slot}".restartIfChanged
      && !c.systemd.services."mrjam-rust-${slot}".stopIfChanged) slots
      && !c.systemd.services.nginx.restartIfChanged && c.services.nginx.enableReload) [staged promoted];
  };
  valid=lib.all (x: x) (builtins.attrValues checks);
  # Each view forces only one configuration (plus the immutable baseline).
  # The protected caller compares all three views before constructing a plan.
  hash=value: builtins.hashString "sha256" (builtins.toJSON value);
  view=phase: config: effective: {
    schema_version=1;inherit phase candidatePath;
    input_state_sha256=builtins.hashFile "sha256" stateFile;
    state=effective // {system=toString config.system.build.toplevel;};
    assertions_pass=lib.all (a: a.assertion) config.assertions;
    units=lib.mapAttrs (_: unit: builtins.hashString "sha256" unit.text) config.systemd.units;
    routes_sha256=hash config.services.nginx.virtualHosts;
    adopted=toString config.environment.etc."mrjam-delivery-adopted.json".source;
    slot_services=lib.genAttrs slots (slot: hash config.systemd.services."mrjam-rust-${slot}".serviceConfig);
    non_asset_configurations=lib.genAttrs slots (slot:
      hash (builtins.removeAttrs (runtime effective.slots.${slot}.runtime) ["assets"]));
    asset_routes=lib.genAttrs slots (slot: hash
      (map (a: builtins.removeAttrs a ["directory" "manifest_sha256"])
        (runtime effective.slots.${slot}.runtime).assets));
    no_implicit_restart=lib.all (slot: !config.systemd.services."mrjam-rust-${slot}".restartIfChanged
      && !config.systemd.services."mrjam-rust-${slot}".stopIfChanged) slots
      && !config.systemd.services.nginx.restartIfChanged && config.services.nginx.enableReload;
  };
in assert builtins.attrNames state==["active_slot" "adopted"]++lib.optional (state ? control_plane) "control_plane"++["schema_version" "slots" "system"]++lib.optional (state ? vise) "vise";
assert !(state ? vise) || (builtins.attrNames state.vise==["adopted" "artifact"] && lib.all store (builtins.attrValues state.vise));
assert !(state ? control_plane) || (builtins.elem (builtins.attrNames state.control_plane)
  [["acceptance" "preparation"] ["acceptance" "preparation" "staging"] ["acceptance" "preparation" "stack" "staging"]]
  && lib.all store (builtins.attrValues state.control_plane));
assert state.schema_version==1 && builtins.elem state.active_slot slots && builtins.attrNames state.slots==slots;
assert store state.system && store state.adopted && store candidatePath;
assert lib.all (slot: builtins.attrNames state.slots.${slot}==["runtime" "server"]
  && lib.all store [state.slots.${slot}.runtime state.slots.${slot}.server]) slots;
assert candidate.schema_version==1 && !candidate.deployment_authorized && candidate.slot==off;
assert bundle.proposal_sha256==candidate.proposal_sha256 && bundle.slot==off && !bundle.deployment_authorized;
{
  views={current=view "current" before state;stage=view "stage" staged stagedState;
    promotion=view "promotion" promoted promotedState;};
  # Content builds only; these attributes alone never authorize activation.
  # Use the separately verified views and retain the resulting exact paths.
  builds={stage=staged.system.build.toplevel;promotion=promoted.system.build.toplevel;};
  evaluation={inherit checks;current=toString before.system.build.toplevel;
    baselineSystem=toString base.system.build.toplevel;inherit baseSlots;
    normalizedUnitChanges=builtins.filter (name: base.systemd.units.${name}.text!=before.systemd.units.${name}.text) names;
    baselineDependencies=map toString base.system.extraDependencies;
    normalizedDependencies=map toString before.system.extraDependencies;
    staged=toString staged.system.build.toplevel;promoted=toString promoted.system.build.toplevel;
    stagedChanged=changed staged;promotedChanged=changed promoted;
    stagedState=stagedState // {system=toString staged.system.build.toplevel;};
    promotedState=promotedState // {system=toString promoted.system.build.toplevel;};};
  stage=assert valid;staged.system.build.toplevel;
  promotion=assert valid;promoted.system.build.toplevel;
}
