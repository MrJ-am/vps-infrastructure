# Proposed real bindings only. This expression performs no host operation.
{ controllerRevision }:
let
  nixpkgs = /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source;
  pkgs = import nixpkgs { system = "x86_64-linux"; };
  lib = pkgs.lib;
  policyFile = ../current-validator-v1/authority-policy.proposed.json;
  authorityPolicy = builtins.fromJSON (builtins.readFile policyFile);
  locked = import ../../forgejo/locked-toolchain.nix {};
  canonical = import ../current-validator-v1/bindings.nix { pkgs = locked; };
  # Preserve the qualified closureInfo context, which is bound into producer.
  validator = canonical.validator;
  qualifiedAuthorityPolicy = builtins.fromJSON (builtins.readFile
    /nix/store/d8bhnl18vsch1zbrvm28w6dvn6acz1k6-mrjam-validation-authority-policy.json);
  source = builtins.storePath "/nix/store/qaf21rxsm38vya6kr6pqr5w02z3dbzbv-mrjam-public-proposed-sources-b02-readiness-v1";
  arguments = {
    inherit controllerRevision validator authorityPolicy;
    rulesRevision = "b02bdf1b5d63dcf0e0610723788a7ca7e384932c";
    proposals = [ { inherit source; sha256 = "8177667ea392aacd4c31ae32c03f2e75fd11b15bd716567ad6b412a9cd60defb"; } ];
    policyTokenFile = "/var/lib/mrjam-ci-credentials/forgejo-policy-token";
    registrationTokenFile = "/var/lib/mrjam-ci-credentials/forgejo-registration-token";
    signingKeyFile = "/var/lib/mrjam-validation-authority/signing-key";
    enableBoundedActions = false;
  };
  evaluate = extra: (import (nixpkgs + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux";
    modules = [ ../../hosts/mrjam-vps/candidate-unicast.nix ] ++ extra;
  }).config;
  previous = evaluate [ ];
  proposed = evaluate [ (import ../host-profile-authority-report-v3.nix arguments) ];
  changed = lib.filter (name: !(builtins.hasAttr name proposed.systemd.units)
    || proposed.systemd.units.${name}.text != previous.systemd.units.${name}.text)
    (builtins.attrNames previous.systemd.units);
  apps = [ "forgejo" "nginx" "postgresql" "kanidm" "phpfpm-nextcloud" "redis-nextcloud"
    "mrjam-rust-blue" "mrjam-rust-green" "mrjam-identity" "mrjam-identity-deletion"
    "mrjam-vision-admission" "mrjam-vision-archive" "mrjam-vision-closure" "mrjam-vision-cycle"
    "mrjam-vision-replay" "vision-embeddings" ];
  services = [ "mrjam-forgejo-policy" "mrjam-forgejo-registration" "mrjam-forgejo-runner"
    "mrjam-validation-worker@" "mrjam-validation-collector@" "mrjam-validation-staging"
    "mrjam-validation-export@" "mrjam-validation-authority" ];
  sockets = [ "mrjam-validation-worker" "mrjam-validation-collector" "mrjam-validation-export" "mrjam-validation-authority" ];
  checks = {
    assertionsPass = lib.all (a: a.assertion) proposed.assertions;
    canonicalValidatorExact = toString validator == "/nix/store/aj0m8465xcx0fzg03lkrvlnbxvldy6zm-mrjam-validate-current-readiness-1";
    qualifiedAuthorityExact = toString proposed.services.mrjamValidationAuthority.package == "/nix/store/cqz4jlhpis05gj4wcjgaddb45qbfwpz0-mrjam-validation-authority-report-details-3";
    qualifiedNativeProducerExact = proposed.services.mrjamValidationAuthority.producerBinding == qualifiedAuthorityPolicy.producer;
    policySourceUnchanged = builtins.hashFile "sha256" policyFile == "1ff6b41359b97b7641379386a69c76bf10c9b38ab694cfabd49c67ae3ed4aa66";
    actualPublicKeyBound = authorityPolicy.key_id == "f0e41983bbc2c2ff0bc1ccda81156d2e0b26f146d7dd0ec7497d03e2810fb758";
    baselineMatchesDeployed = toString previous.system.build.toplevel == "/nix/store/phi68cwg38madbq8p805yvrsyry8g8wr-nixos-system-srv1982677-26.05pre-git";
    applicationUnitBytesPreserved = lib.all (name: proposed.systemd.units."${name}.service".text == previous.systemd.units."${name}.service".text) apps;
    firewallUnitBytesPreserved = proposed.systemd.units."firewall.service".text == previous.systemd.units."firewall.service".text;
    existingUnitDeltaOnlyMaintenanceTriggers = changed == [ "dbus-broker.service" "systemd-tmpfiles-resetup.service" ];
    llmnrRemainsDisabled = !proposed.services.resolved.settings.Resolve.LLMNR;
    actionsRemainDisabled = !proposed.services.mrjamForgejoHost.enableBoundedActions;
    policyRemainsPlanOnly = proposed.services.mrjamForgejoPolicy.mode == "plan" && proposed.services.mrjamForgejoPolicy.reviewedPlan == null;
    noCIServiceImplicitStart = lib.all (name: proposed.systemd.services.${name}.wantedBy == [ ]) services;
    noCISocketImplicitStart = lib.all (name: proposed.systemd.sockets.${name}.wantedBy == [ ]) sockets;
    keyReferenceExact = proposed.services.mrjamValidationAuthority.signingKeyFile == arguments.signingKeyFile;
    separateFutureCredentialReferences = arguments.policyTokenFile != arguments.registrationTokenFile && arguments.registrationTokenFile != arguments.signingKeyFile;
  };
in {
  evaluation = {
    schema_version = 1;
    scope = "proposed actual bindings; rules not yet adopted; credentials absent; no activation";
    inherit checks controllerRevision arguments;
    proposed_toplevel = toString proposed.system.build.toplevel;
    changed_existing_units = changed;
    added_units = lib.subtractLists (builtins.attrNames previous.systemd.units) (builtins.attrNames proposed.systemd.units);
    removed_units = lib.subtractLists (builtins.attrNames proposed.systemd.units) (builtins.attrNames previous.systemd.units);
  };
  toplevel = assert lib.all (x: x) (builtins.attrValues checks); proposed.system.build.toplevel;
}
