# Data-only observed host state plus a fixed, qualified controller/backup recipe.
# Build and compare before activation; this expression never activates anything.
{ stateFile }:
let
  nixpkgs=/nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source;
  pkgs=import nixpkgs {}; lib=pkgs.lib;
  baseline=import ./acceptance-host.nix;
  state=builtins.fromJSON (builtins.unsafeDiscardStringContext (builtins.readFile stateFile));
  preparation="/nix/store/p0rsqcgy8jyvpbapjhci8dbwmlyryk1s-mrjam-delivery-preparation-1";
  evaluate=modules: (import (nixpkgs+"/nixos/lib/eval-config.nix") {system="x86_64-linux";inherit modules;}).config;
  base=evaluate baseline.modules;
  slots=["blue" "green"];
  store=p: builtins.isString p && builtins.match "/nix/store/[0-9abcdfghijklmnpqrsvwxyz]{32}-[A-Za-z0-9+._-]+" p!=null;
  overlay={
    mrjamVpsApplications.activeSlot=lib.mkOverride (-10) state.active_slot;
    mrjamVpsApplications.slots=lib.genAttrs slots (s: lib.mkIf (state.slots.${s}.runtime!=base.mrjamVpsApplications.slots.${s}) (lib.mkOverride (-10) state.slots.${s}.runtime));
    services.mrjamRust.slots=lib.genAttrs slots (s: {artifactStorePath=lib.mkIf (state.slots.${s}.server!=base.services.mrjamRust.slots.${s}.artifactStorePath) (lib.mkOverride (-10) state.slots.${s}.server);});
    services.mrjamIntakePreparation.adopted=lib.mkIf (state.adopted!=toString base.services.mrjamIntakePreparation.adopted) (lib.mkOverride (-10) (builtins.storePath state.adopted));
    systemd.services=lib.genAttrs (map (s: "mrjam-rust-${s}") slots) (n: {wantedBy=lib.mkOverride (-10) (lib.optional (n=="mrjam-rust-${state.active_slot}") "multi-user.target");});
    system.extraDependencies=lib.concatMap (s:
      lib.optional (state.slots.${s}.server!=base.services.mrjamRust.slots.${s}.artifactStorePath) (builtins.storePath state.slots.${s}.server)
      ++lib.optional (state.slots.${s}.runtime!=base.mrjamVpsApplications.slots.${s}) (builtins.storePath state.slots.${s}.runtime)) slots;
  };
  modules=control: baseline.modules++[(import ./delivery-control-plane.nix {inherit control;}) overlay];
  before=evaluate (modules state.control_plane);
  after=evaluate ((modules (state.control_plane//{inherit preparation;}))++[./delivery-vise-backup-baseline.nix]);
  names=builtins.attrNames before.systemd.units;
  changed=builtins.filter (n: before.systemd.units.${n}.text!=after.systemd.units.${n}.text) names;
  added=builtins.filter (n: !(builtins.hasAttr n before.systemd.units)) (builtins.attrNames after.systemd.units);
  backupDirectory="d /var/backup/mrjam/vise-v1 0700 root root -";
  database=c: {
    inherit (c.services.postgresql) enable enableJIT dataDir port authentication identMap settings
      initialScript ensureUsers ensureDatabases;
    package=toString c.services.postgresql.package;
    finalPackage=toString c.services.postgresql.finalPackage;
    unit=c.systemd.units."postgresql.service".text;
  };
  checks={
    baselineExact=toString before.system.build.toplevel==state.system;
    assertionsPass=lib.all (a: a.assertion) after.assertions;
    unitsPreserved=lib.all (n: builtins.hasAttr n after.systemd.units) names;
    onlyPreparationAndDirectorySetupChanged=changed==["mrjam-delivery-preparation.service" "systemd-tmpfiles-resetup.service"];
    onlyBackupDirectoryAdded=!(builtins.elem backupDirectory before.systemd.tmpfiles.rules)
      && lib.count (r: r==backupDirectory) after.systemd.tmpfiles.rules==1
      && lib.filter (r: r!=backupDirectory) after.systemd.tmpfiles.rules==before.systemd.tmpfiles.rules
      && before.systemd.tmpfiles.settings==after.systemd.tmpfiles.settings
      && lib.count (p: lib.getName p=="nixos-tmpfiles.d") before.systemd.tmpfiles.packages==1
      && lib.count (p: lib.getName p=="nixos-tmpfiles.d") after.systemd.tmpfiles.packages==1
      && map toString (lib.filter (p: lib.getName p!="nixos-tmpfiles.d") before.systemd.tmpfiles.packages)
        ==map toString (lib.filter (p: lib.getName p!="nixos-tmpfiles.d") after.systemd.tmpfiles.packages);
    onlyBackupAdded=added==["mrjam-vise-backup-recovery.service" "mrjam-vise-backup-recovery.timer" "mrjam-vise-backup.service" "mrjam-vise-backup.timer"];
    routesUnchanged=before.services.nginx.virtualHosts==after.services.nginx.virtualHosts;
    adoptedUnchanged=before.environment.etc."mrjam-delivery-adopted.json".source==after.environment.etc."mrjam-delivery-adopted.json".source;
    databasesUnchanged=database before==database after;
    credentialsUnchanged=before.systemd.services.mrjam-delivery-preparation.serviceConfig.LoadCredential==after.systemd.services.mrjam-delivery-preparation.serviceConfig.LoadCredential;
    # Compare effective values; forcing an entire NixOS submodule also forces
    # optional settings which deliberately have no configured value.
    viseUnchanged=before.systemd.units."vise.service".text==after.systemd.units."vise.service".text
      && before.systemd.services.vise.wantedBy==after.systemd.services.vise.wantedBy
      && before.systemd.services.vise.restartIfChanged==after.systemd.services.vise.restartIfChanged
      && before.systemd.services.vise.stopIfChanged==after.systemd.services.vise.stopIfChanged;
  };
in assert builtins.attrNames state==["active_slot" "adopted" "control_plane" "schema_version" "slots" "system"];
assert state.schema_version==1 && builtins.elem state.active_slot slots && builtins.attrNames state.slots==slots;
assert store state.system && store state.adopted;
assert lib.all (s: builtins.attrNames state.slots.${s}==["runtime" "server"] && lib.all store (builtins.attrValues state.slots.${s})) slots;
{
  evaluation={inherit checks changed added;previous=toString before.system.build.toplevel;system=toString after.system.build.toplevel;
    state=state//{system=toString after.system.build.toplevel;control_plane=state.control_plane//{inherit preparation;};};};
  toplevel=assert lib.all (x: x) (builtins.attrValues checks);after.system.build.toplevel;
}
