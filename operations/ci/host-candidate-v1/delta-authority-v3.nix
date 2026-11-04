# Compare proposed CI installations only; neither is active or boot-selected.
{ controllerRevision }:
let
  nixpkgs = /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source;
  pkgs = import nixpkgs { system = "x86_64-linux"; };
  lib = pkgs.lib;
  args = (import ./evaluation-v3.nix { inherit controllerRevision; }).evaluation.arguments;
  evaluate = profile: (import (nixpkgs + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux";
    modules = [ ../../hosts/mrjam-vps/candidate-unicast.nix (import profile args) ];
  }).config;
  before = evaluate ../host-profile.nix;
  after = evaluate ../host-profile-authority-report-v3.nix;
  oldPackage = toString before.services.mrjamValidationAuthority.package;
  newPackage = toString after.services.mrjamValidationAuthority.package;
  oldCoordinator = toString before.services.mrjamValidationCoordinatorAttestation.package;
  newCoordinator = toString after.services.mrjamValidationCoordinatorAttestation.package;
  oldRoot = toString before.services.mrjamValidationCoordinatorAttestation.root;
  newRoot = toString after.services.mrjamValidationCoordinatorAttestation.root;
  oldEtc = toString before.system.build.etc;
  newEtc = toString after.system.build.etc;
  names = builtins.attrNames before.systemd.units;
  changed = lib.filter (name: before.systemd.units.${name}.text != after.systemd.units.${name}.text) names;
  expected = [ "mrjam-forgejo-runner.service" "mrjam-validation-authority.service" "mrjam-validation-collector@.service"
    "mrjam-validation-export@.service" "mrjam-validation-worker@.service" ];
  checks = {
    assertionsPass = lib.all (x: x.assertion) (before.assertions ++ after.assertions);
    oldAuthorityExact = oldPackage == "/nix/store/19r3a6ylzp32vg3bkfr9wfhd1n8cwm71-mrjam-validation-authority-credentials-2";
    newAuthorityExact = newPackage == "/nix/store/cqz4jlhpis05gj4wcjgaddb45qbfwpz0-mrjam-validation-authority-report-details-3";
    unitNamesIdentical = names == builtins.attrNames after.systemd.units;
    onlyFourAuthorityConsumersAndCoordinatorChange = changed == expected;
    allUnitTextIdenticalAfterPackageSubstitution = lib.all (name:
      before.systemd.units.${name}.text == builtins.replaceStrings
        [ newPackage newCoordinator newRoot ] [ oldPackage oldCoordinator oldRoot ] after.systemd.units.${name}.text) names;
    publicPolicyUnchanged = before.services.mrjamValidationAuthority.policy == after.services.mrjamValidationAuthority.policy;
    producerUnchanged = before.services.mrjamValidationAuthority.producerBinding == after.services.mrjamValidationAuthority.producerBinding;
    activationScriptOnlyEtcReferenceChanges = before.system.activationScripts.script ==
      builtins.replaceStrings [ newEtc ] [ oldEtc ] after.system.activationScripts.script;
    usersAndGroupsUnchanged = before.system.activationScripts.users.text == after.system.activationScripts.users.text;
    credentialsRemainPrivateReferences = args.policyTokenFile == "/var/lib/mrjam-ci-credentials/forgejo-policy-token"
      && args.registrationTokenFile == "/var/lib/mrjam-ci-credentials/forgejo-registration-token"
      && args.signingKeyFile == "/var/lib/mrjam-validation-authority/signing-key";
    actionsRemainDisabled = !after.services.mrjamForgejoHost.enableBoundedActions;
  };
in {
  schema_version = 1;
  scope = "authority package substitution in two inactive proposed CI compositions; no build or activation";
  inherit controllerRevision oldPackage newPackage oldCoordinator newCoordinator oldRoot newRoot oldEtc newEtc checks changed;
  all_passed = lib.all (x: x) (builtins.attrValues checks);
  unit_count = builtins.length names;
  before_toplevel = toString before.system.build.toplevel;
  after_toplevel = toString after.system.build.toplevel;
  changed_unit_hashes = map (name: { inherit name;
    before_sha256 = builtins.hashString "sha256" before.systemd.units.${name}.text;
    after_sha256 = builtins.hashString "sha256" after.systemd.units.${name}.text;
  }) changed;
}
