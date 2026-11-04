# Stage signed artifacts in the off-traffic slot; no route or adopted-base move.
let
  nixpkgs=/nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source;
  lib=(import nixpkgs {}).lib;
  baseline=import ./runner-admission-mounts-host.nix;
  # Keep this observed generation reproducible while subsequent controllers
  # are developed. Retain the derivation context rather than silently dropping
  # the installed controller from the system closure.
  fixedBaseline=baseline.modules++[{
    services.mrjamAdmissionController.package=lib.mkOverride 20
      (builtins.appendContext "/nix/store/dlphwj3kmxmljjg4dj6flihqah9jghgy-mrjam-protected-admission-controller-1" {
        "/nix/store/l7545y7kcr7jcwz186f3k5lwq2656b1d-mrjam-protected-admission-controller-1.drv"={outputs=["out"];};
      });
  }];
  bundle=import ./accepted-e06-bundle.nix;
  replacement=import ./slot-artifacts.nix {
    slot="blue";
    serverStorePath=builtins.unsafeDiscardStringContext (toString bundle.server);
    runtimeStorePath=builtins.unsafeDiscardStringContext (toString bundle.runtime);
  };
  evaluate=extra: (import (nixpkgs+"/nixos/lib/eval-config.nix") {
    system="x86_64-linux";modules=fixedBaseline++extra;
  }).config;
  before=evaluate [];after=evaluate [replacement];
  names=builtins.attrNames before.systemd.units;
  changed=builtins.filter (name: before.systemd.units.${name}.text!=after.systemd.units.${name}.text) names;
  oldRuntime=builtins.fromJSON (builtins.unsafeDiscardStringContext (builtins.readFile (before.mrjamVpsApplications.slots.blue+"/runtime.json")));
  newRuntime=builtins.fromJSON (builtins.unsafeDiscardStringContext (builtins.readFile (bundle.runtime+"/runtime.json")));
  checks={
    baselineExact=toString before.system.build.toplevel=="/nix/store/mp6b02wzn3pj5fn1g8j8gp9nzfr4fsq0-nixos-system-srv1982677-26.05pre-git";
    assertionsPass=lib.all (a: a.assertion) after.assertions;
    onlyOffTrafficUnitChanges=changed==["mrjam-rust-blue.service"];
    noUnitAdded=names==builtins.attrNames after.systemd.units;
    activeSlotStillGreen=before.mrjamVpsApplications.activeSlot=="green" && after.mrjamVpsApplications.activeSlot=="green";
    routesUnchanged=before.services.nginx.virtualHosts==after.services.nginx.virtualHosts;
    nonAssetConfigurationUnchanged=builtins.removeAttrs oldRuntime ["assets"]==builtins.removeAttrs newRuntime ["assets"];
    assetRoutingUnchanged=map (a: builtins.removeAttrs a ["directory" "manifest_sha256"]) oldRuntime.assets
      ==map (a: builtins.removeAttrs a ["directory" "manifest_sha256"]) newRuntime.assets;
    noImplicitRestart= !after.systemd.services.mrjam-rust-blue.restartIfChanged && !after.systemd.services.mrjam-rust-blue.stopIfChanged;
    bootPolicyUnchanged=before.systemd.services.mrjam-rust-blue.wantedBy==after.systemd.services.mrjam-rust-blue.wantedBy;
    adoptedUnchanged=before.environment.etc."mrjam-delivery-adopted.json".source==after.environment.etc."mrjam-delivery-adopted.json".source;
  };
in {
  modules=fixedBaseline++[replacement];
  evaluation={inherit checks changed;system=toString after.system.build.toplevel;};
  toplevel=assert lib.all (x: x) (builtins.attrValues checks);after.system.build.toplevel;
}
