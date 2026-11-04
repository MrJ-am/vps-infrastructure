# Candidate only. Evaluation/build neither publishes admissions nor activates CI.
let
  nixpkgs=/nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source;
  lib=(import nixpkgs {}).lib;
  locked=import ../../forgejo/locked-toolchain.nix {};
  baseline=import ./reload-host.nix;
  authority=import ./admission-package.nix {};
  addition={config,...}: {
    disabledModules=[{key="mrjam-ci-locked:${toString ../authority-report-details-v3/module.nix}";}];
    imports=[./admission-module.nix];
    services.mrjamValidationAuthority.policy=lib.mkForce (builtins.removeAttrs authority.policy ["producer"]);
    services.mrjamValidationWorker.validator=lib.mkForce authority.bindings.validator;
    services.mrjamValidationStaging.proposals=lib.mkForce (before.services.mrjamValidationStaging.proposals ++ [{
      sha256=authority.bindings.proposal;source=authority.bindings.source;
    }]);
    environment.etc."mrjam-validation-authority/producer.json".text=lib.mkForce (builtins.toJSON authority.producer);
    systemd.tmpfiles.rules=["d /var/lib/mrjam-validation-admissions 0755 root root -"];
    systemd.services.mrjam-forgejo-runner.serviceConfig={
      BindReadOnlyPaths=["/var/lib/mrjam-validation-admissions"];
      RootDirectory=lib.mkOverride 40 (locked.runCommand "mrjam-admitted-coordinator-root" {} ''
        mkdir -p "$out"
        cp -a --reflink=auto ${config.services.mrjamValidationCoordinatorAttestation.root}/. "$out/"
        chmod u+w "$out/var" "$out/var/lib"
        mkdir -p "$out/var/lib/mrjam-validation-admissions"
      '');
    };
  };
  evaluate=extra: (import (nixpkgs+"/nixos/lib/eval-config.nix") {
    system="x86_64-linux";modules=baseline.modules++extra;
  }).config;
  before=evaluate [];after=evaluate [addition];
  names=builtins.attrNames before.systemd.units;
  changed=builtins.filter (name: before.systemd.units.${name}.text!=after.systemd.units.${name}.text) names;
  allowed=["mrjam-forgejo-runner.service" "mrjam-validation-worker@.service"
    "mrjam-validation-collector@.service" "mrjam-validation-export@.service"
    "mrjam-validation-authority.service" "systemd-tmpfiles-resetup.service"];
  checks={
    baselineExact=toString before.system.build.toplevel=="/nix/store/xqbbs66wf4q9n7fdrs9p54bf87ak264a-nixos-system-srv1982677-26.05pre-git";
    assertionsPass=lib.all (a: a.assertion) after.assertions;
    onlyCIUnitsChanged=lib.all (name: builtins.elem name allowed) changed;
    noUnitsAdded=builtins.attrNames after.systemd.units==names;
    routesUnchanged=before.services.nginx.virtualHosts==after.services.nginx.virtualHosts;
    slotUnchanged=before.mrjamVpsApplications.activeSlot==after.mrjamVpsApplications.activeSlot;
    exactProducer=after.services.mrjamValidationAuthority.producerBinding==authority.producer;
    previousSourceRetained=lib.all (entry: builtins.elem entry after.services.mrjamValidationStaging.proposals)
      before.services.mrjamValidationStaging.proposals;
  };
in {
  modules=baseline.modules++[addition];
  evaluation={inherit checks changed;system=toString after.system.build.toplevel;};
  toplevel=assert lib.all (x: x) (builtins.attrValues checks);after.system.build.toplevel;
}
