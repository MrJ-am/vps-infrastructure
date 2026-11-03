{ nixpkgs }:
let
  locked = import ../../forgejo/locked-toolchain.nix {};
  proposed = import ../current-validator-v1/bindings.nix { pkgs = locked; };
  policy = builtins.fromJSON (builtins.readFile ../current-validator-v1/authority-policy.proposed.json);
  evaluate = updated: (import (nixpkgs + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux";
    modules = [ ../modules.nix {
      disabledModules = if updated then [ { key = "mrjam-ci-locked:${toString ../authority-credentials-v2/module.nix}"; } ] else [];
      system.stateVersion = "26.05"; boot.loader.grub.enable = false;
      fileSystems."/" = { device = "synthetic-evaluation-only"; fsType = "ext4"; };
      networking.nftables.enable = true;
      services.mrjamForgejoPolicy = { enable = true; mode = "plan"; phase = "operate-validation";
        rulesRevision = policy.rules_revision; controllerRevision = "2222222222222222222222222222222222222222";
        tokenFile = "/run/synthetic-evaluation-only/policy"; };
      services.mrjamForgejoRunner = { enable = true; rulesRevision = policy.rules_revision;
        coordinatorUid = 950; registrarUid = 949; registrationTokenFile = "/run/synthetic-evaluation-only/registration"; };
      services.mrjamValidationWorker = { enable = true; rulesRevision = policy.rules_revision; validator = proposed.validator; };
      services.mrjamValidationCollector = { enable = true; rulesRevision = policy.rules_revision; };
      users.users.mrjam-validation-worker.uid = 951;
      users.users.mrjam-validation-collector.uid = 952;
      services.mrjamValidationStaging = { enable = true; proposals = [{ inherit (proposed.staging) source sha256; }]; };
      services.mrjamValidationAuthority = { enable = true; inherit policy; signingKeyFile = "/var/lib/mrjam-validation-authority/signing-key"; };
    } ] ++ (if updated then [ (args@{ ... }: import ./module.nix (args // { pkgs = locked; })) ] else []);
  }).config;
  before = evaluate false; after = evaluate true;
  oldPackage = before.services.mrjamValidationAuthority.package;
  newPackage = after.services.mrjamValidationAuthority.package;
  names = [ "mrjam-validation-worker@" "mrjam-validation-collector@" "mrjam-validation-export@" "mrjam-validation-authority" ];
  normalize = package: unit: unit // { ExecStart = builtins.replaceStrings [ (toString package) ] [ "IMMUTABLE_AUTHORITY_PACKAGE" ] unit.ExecStart; };
  results = {
    bothAssertionsPass = builtins.all (x: x.assertion) (before.assertions ++ after.assertions);
    newPackageExact = toString newPackage == "/nix/store/cqz4jlhpis05gj4wcjgaddb45qbfwpz0-mrjam-validation-authority-report-details-3";
    oldPackageExact = toString oldPackage == "/nix/store/19r3a6ylzp32vg3bkfr9wfhd1n8cwm71-mrjam-validation-authority-credentials-2";
    producerUnchanged = before.services.mrjamValidationAuthority.producerBinding == after.services.mrjamValidationAuthority.producerBinding;
    publicPolicyUnchanged = before.services.mrjamValidationAuthority.policy == after.services.mrjamValidationAuthority.policy;
    serviceRestrictionsUnchanged = builtins.all (name: normalize oldPackage before.systemd.services.${name}.serviceConfig == normalize newPackage after.systemd.services.${name}.serviceConfig) names;
    socketRestrictionsUnchanged = builtins.all (name: before.systemd.sockets.${name}.socketConfig == after.systemd.sockets.${name}.socketConfig) [ "mrjam-validation-authority" "mrjam-validation-export" ];
    noAutomaticAuthorityStart = after.systemd.services.mrjam-validation-authority.wantedBy == [] && after.systemd.sockets.mrjam-validation-authority.wantedBy == [];
    sameExactPrivateKeyReference = after.systemd.services.mrjam-validation-authority.serviceConfig.LoadCredential == [ "signing-key:/var/lib/mrjam-validation-authority/signing-key" ];
    sameDistinctIdentities = after.users.users.mrjam-validation-authority.uid == 953 && after.users.users.mrjam-validation-collector.uid == 952 && after.services.mrjamForgejoRunner.coordinatorUid == 950;
  };
in { inherit results; all_passed = builtins.all (x: x) (builtins.attrValues results); package = newPackage.outPath;
  scope = "Two isolated NixOS evaluations, no activation or new systemd VM; filesystem/controller/token references are invented."; }
