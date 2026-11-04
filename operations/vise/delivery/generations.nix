# Fixed host composition plus observed data. This evaluates/builds, never switches.
{ stateFile, candidatePath, currentVise ? null }:
let
  nixpkgs=/nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source;
  lib=(import nixpkgs {}).lib;
  # Reproduce the installed composition from its qualified immutable recipe.
  # Pending local controller edits must not silently alter the existing host.
  baselineRecipe=builtins.storePath "/nix/store/dnir95r62s6xi57dcygv80fqhirkhzas-mrjam-protected-delivery-recipe-1";
  baseline=import (baselineRecipe+"/operations/ci/continuous-delivery-v1/acceptance-host.nix");
  state=builtins.fromJSON (builtins.unsafeDiscardStringContext (builtins.readFile stateFile));
  oldVise=if currentVise!=null then currentVise else state.vise or null;
  store=p: builtins.isString p && builtins.match "/nix/store/[0-9abcdfghijklmnpqrsvwxyz]{32}-[A-Za-z0-9+._-]+" p!=null;
  candidate=builtins.fromJSON (builtins.unsafeDiscardStringContext
    (builtins.readFile (builtins.storePath candidatePath+"/descriptor.json")));
  content=builtins.fromJSON (builtins.unsafeDiscardStringContext
    (builtins.readFile (builtins.storePath candidate.bundle+"/artifact.json")));
  evaluate=extra: (import (nixpkgs+"/nixos/lib/eval-config.nix") {
    system="x86_64-linux";
    modules=baseline.modules++[
      (import ../../ci/continuous-delivery-v1/delivery-control-plane.nix {control=state.control_plane;})
      (baselineRecipe+"/operations/ci/continuous-delivery-v1/delivery-vise-backup-baseline.nix")
    ]++extra;
  }).config;
  base=evaluate [];
  slots=["blue" "green"];
  platform={
    mrjamVpsApplications.activeSlot=lib.mkOverride (-10) state.active_slot;
    mrjamVpsApplications.slots=lib.genAttrs slots (s: 
      lib.mkIf (state.slots.${s}.runtime!=base.mrjamVpsApplications.slots.${s})
        (lib.mkOverride (-10) state.slots.${s}.runtime));
    services.mrjamRust.slots=lib.genAttrs slots (s:  {
      artifactStorePath=lib.mkIf (state.slots.${s}.server!=base.services.mrjamRust.slots.${s}.artifactStorePath)
        (lib.mkOverride (-10) state.slots.${s}.server);
    });
    services.mrjamIntakePreparation.adopted=lib.mkIf (state.adopted!=toString base.services.mrjamIntakePreparation.adopted)
      (lib.mkOverride (-10) (builtins.storePath state.adopted));
    systemd.services=lib.genAttrs (map (s: "mrjam-rust-${s}") slots) (name: {
      wantedBy=lib.mkOverride (-10) (lib.optional (name=="mrjam-rust-${state.active_slot}") "multi-user.target");
    });
    system.extraDependencies=lib.concatMap (s: 
      lib.optional (state.slots.${s}.server!=base.services.mrjamRust.slots.${s}.artifactStorePath) (builtins.storePath state.slots.${s}.server)
      ++lib.optional (state.slots.${s}.runtime!=base.mrjamVpsApplications.slots.${s}) (builtins.storePath state.slots.${s}.runtime)) slots;
  };
  vise=v: {
    services.mrjamVise.artifactRoot=lib.mkOverride (-10) v.artifact;
    environment.etc."mrjam-vise-delivery-adopted.json".source=builtins.storePath v.adopted;
    system.extraDependencies=[(builtins.storePath v.artifact)];
  };
  before=evaluate ([platform]++lib.optional (oldVise!=null) (vise oldVise));
  after=evaluate [platform (vise {artifact=candidate.bundle;adopted=candidate.adopted;})];
  names=builtins.attrNames before.systemd.units;
  changed=lib.filter (n:  before.systemd.units.${n}.text!=after.systemd.units.${n}.text) names;
  v=c: c.systemd.services.vise;
  checks={
    currentExact=toString before.system.build.toplevel==state.system;
    assertionsPass=lib.all (c: lib.all (a: a.assertion) c.assertions) [before after];
    sameUnits=names==builtins.attrNames after.systemd.units;
    onlyViseUnitChanges=lib.all (n: n=="vise.service") changed;
    routesUnchanged=before.services.nginx.virtualHosts==after.services.nginx.virtualHosts;
    platformAdoptionUnchanged=before.environment.etc."mrjam-delivery-adopted.json".source==after.environment.etc."mrjam-delivery-adopted.json".source;
    identityAndLimitsUnchanged=builtins.removeAttrs (v before).serviceConfig ["ExecStart"]==builtins.removeAttrs (v after).serviceConfig ["ExecStart"];
    runtimeEnvironmentUnchanged=builtins.removeAttrs (v before).environment ["CARNET_DIST"]==builtins.removeAttrs (v after).environment ["CARNET_DIST"];
    schemaPreflightUnchanged=(v before).preStart==(v after).preStart;
    bootPolicyUnchanged=(v before).wantedBy==(v after).wantedBy;
    noImplicitRestart=!(v after).restartIfChanged && !(v after).stopIfChanged;
    backupEnabled=after.services.mrjamViseCoherentBackup.enable && after.services.mrjamViseCoherentBackup.promote;
  };
  valid=lib.all (x: x) (builtins.attrValues checks);
  hash=value: builtins.hashString "sha256" (builtins.toJSON value);
  view=phase: c: {
    schema_version=1;profile="vise-v1";inherit phase candidatePath;
    input_state_sha256=builtins.hashFile "sha256" stateFile;
    system=toString c.system.build.toplevel;
    assertions_pass=lib.all (a: a.assertion) c.assertions;
    units=lib.mapAttrs (_: unit: builtins.hashString "sha256" unit.text) c.systemd.units;
    routes=hash c.services.nginx.virtualHosts;
    platform_adopted=toString c.environment.etc."mrjam-delivery-adopted.json".source;
    artifact=c.services.mrjamVise.artifactRoot;
    adopted=if c.environment.etc ? "mrjam-vise-delivery-adopted.json"
      then toString c.environment.etc."mrjam-vise-delivery-adopted.json".source else null;
    identity_limits=hash (builtins.removeAttrs (v c).serviceConfig ["ExecStart"]);
    environment=hash (builtins.removeAttrs (v c).environment ["CARNET_DIST"]);
    preflight=hash (v c).preStart;boot=hash (v c).wantedBy;
    no_implicit_restart=!(v c).restartIfChanged && !(v c).stopIfChanged;
    backup_enabled=c.services.mrjamViseCoherentBackup.enable && c.services.mrjamViseCoherentBackup.promote;
  };
in assert builtins.attrNames state==["active_slot" "adopted" "control_plane" "schema_version" "slots" "system"]++lib.optional (state ? vise) "vise";
assert state.schema_version==1 && builtins.elem state.active_slot slots && builtins.attrNames state.slots==slots;
assert lib.all store [state.system state.adopted candidatePath candidate.bundle candidate.adopted];
assert lib.all (s: builtins.attrNames state.slots.${s}==["runtime" "server"] && lib.all store (builtins.attrValues state.slots.${s})) slots;
assert oldVise==null || (builtins.attrNames oldVise==["adopted" "artifact"] && lib.all store (builtins.attrValues oldVise));
assert currentVise==null || !(state ? vise) || currentVise==state.vise;
assert candidate.schema_version==2 && candidate.profile=="vise-v1" && !candidate.deployment_authorized;
assert content.profile=="vise-v1" && content.proposal_sha256==candidate.proposal_sha256 && !content.deployment_authorized;
{
  # Evaluate these separately; the protected caller must compare both views
  # before building/using the candidate, just as for platform generations.
  views={current=view "current" before;candidate=view "candidate" after;};
  build=after.system.build.toplevel;
  evaluation={inherit checks changed;previous=toString before.system.build.toplevel;system=toString after.system.build.toplevel;
    vise={artifact=candidate.bundle;adopted=candidate.adopted;};};
  toplevel=assert valid;after.system.build.toplevel;
}
