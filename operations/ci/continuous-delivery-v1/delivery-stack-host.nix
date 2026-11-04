# Compare a protected stack upgrade against the exact observed application state.
{stateFile, stackPath, baselineRecipePath}:
let
  nixpkgs=/nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source;
  lib=(import nixpkgs {}).lib;
  frozen=builtins.storePath "/nix/store/dnir95r62s6xi57dcygv80fqhirkhzas-mrjam-protected-delivery-recipe-1";
  installed=builtins.storePath baselineRecipePath;
  baseline=import (frozen+"/operations/ci/continuous-delivery-v1/acceptance-host.nix");
  state=builtins.fromJSON (builtins.unsafeDiscardStringContext (builtins.readFile stateFile));
  stack=builtins.fromJSON (builtins.unsafeDiscardStringContext
    (builtins.readFile (builtins.storePath stackPath+"/descriptor.json")));
  control=(lib.getAttrs ["acceptance" "preparation" "staging"] stack.packages)//{stack=stackPath;};
  evaluate=mods: (import (nixpkgs+"/nixos/lib/eval-config.nix") {system="x86_64-linux";modules=mods;}).config;
  modules=plane: c: baseline.modules++[(import plane {control=c;})
    (frozen+"/operations/ci/continuous-delivery-v1/delivery-vise-backup-baseline.nix")];
  beforeModules=modules (installed+"/operations/ci/continuous-delivery-v1/delivery-control-plane.nix");
  afterModules=modules ./delivery-control-plane.nix;
  base=evaluate (beforeModules state.control_plane);
  slots=["blue" "green"];
  overlay={config=lib.mkMerge [{
    mrjamVpsApplications.activeSlot=lib.mkOverride (-10) state.active_slot;
    mrjamVpsApplications.slots=lib.genAttrs slots (s:
      lib.mkIf (state.slots.${s}.runtime!=base.mrjamVpsApplications.slots.${s})
        (lib.mkOverride (-10) state.slots.${s}.runtime));
    services.mrjamRust.slots=lib.genAttrs slots (s: {
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
  } (lib.mkIf (state ? vise) {
    services.mrjamVise.artifactRoot=lib.mkOverride (-10) state.vise.artifact;
    environment.etc."mrjam-vise-delivery-adopted.json".source=lib.mkOverride (-10) (builtins.storePath state.vise.adopted);
  })];};
  before=evaluate ((beforeModules state.control_plane)++[overlay]);
  after=evaluate ((afterModules control)++[overlay]);
  names=builtins.attrNames before.systemd.units;
  changed=lib.filter (n: before.systemd.units.${n}.text!=after.systemd.units.${n}.text) names;
  allowed=["mrjam-admission-controller.service" "mrjam-delivery-preparation.service"
    "mrjam-delivery-staging.service" "mrjam-promotion.service" "mrjam-forgejo-runner.service"
    "mrjam-validation-authority.service" "mrjam-validation-export@.service"
    "mrjam-validation-worker@.service" "mrjam-validation-collector@.service"
    "systemd-tmpfiles-resetup.service" "forgejo-backup.service"]
    ++map (s: "mrjam-acceptance-${s}.service") ["mirror" "review" "merge" "sync"];
  checks={
    baselineExact=toString before.system.build.toplevel==state.system;
    assertionsPass=lib.all (a: a.assertion) after.assertions;
    unitNamesPreserved=names==builtins.attrNames after.systemd.units;
    onlyControlServicesChanged=lib.all (n: builtins.elem n allowed) changed;
    serviceBoundariesPreserved=lib.all (unit:
      let name=lib.removeSuffix ".service" unit;
          ignored=["ExecStart"]++lib.optional (name=="mrjam-forgejo-runner") "RootDirectory";
      in builtins.removeAttrs before.systemd.services.${name}.serviceConfig ignored
        ==builtins.removeAttrs after.systemd.services.${name}.serviceConfig ignored)
      (lib.filter (n: n!="systemd-tmpfiles-resetup.service") allowed);
    tmpfilesPerPathPreserved=
      let group=lib.groupBy (line:
        let match=builtins.match "[^ \t]+[ \t]+([^ \t]+).*" line;
        in if match==null then line else builtins.head match);
      in group before.systemd.tmpfiles.rules==group after.systemd.tmpfiles.rules;
    routesPreserved=before.services.nginx.virtualHosts==after.services.nginx.virtualHosts;
    platformAdoptionPreserved=before.environment.etc."mrjam-delivery-adopted.json".source==after.environment.etc."mrjam-delivery-adopted.json".source;
    authorityPackage=toString after.services.mrjamValidationAuthority.package==stack.packages.anchor;
    admissionPackage=toString after.services.mrjamAdmissionController.package==stack.packages.admission;
    stackBound=toString after.environment.etc."mrjam-delivery-stack".source==stackPath;
    runnerRecoveryBound=lib.sort builtins.lessThan after.systemd.services.mrjam-forgejo-runner.wantedBy
      ==["forgejo.service" "multi-user.target"]
      && builtins.elem "forgejo.service" after.systemd.services.mrjam-forgejo-runner.requires
      && builtins.elem "forgejo.service" after.systemd.services.mrjam-forgejo-runner.after
      && after.systemd.services.mrjam-forgejo-runner.serviceConfig.Restart=="no";
  };
in {
  evaluation={inherit checks changed;deployment_authorized=false;
    tmpfiles={
      added=lib.subtractLists before.systemd.tmpfiles.rules after.systemd.tmpfiles.rules;
      removed=lib.subtractLists after.systemd.tmpfiles.rules before.systemd.tmpfiles.rules;
      sameSorted=lib.sort builtins.lessThan before.systemd.tmpfiles.rules==lib.sort builtins.lessThan after.systemd.tmpfiles.rules;
    };
    state=state//{system=toString after.system.build.toplevel;control_plane=control;};
    units=lib.genAttrs allowed (n: after.systemd.units.${n}.text);
  };
  toplevel=assert lib.all (v: v) (builtins.attrValues checks);after.system.build.toplevel;
}
