# Evaluation only: invented rules and an inert verifier, never deployment input.
{ nixpkgs, policyFile ? ../integration-v1/public-fixture-policy.json, detail ? false, delta ? false }:
let
  host = import nixpkgs { system = "x86_64-linux"; };
  lib = host.lib;
  locked = import ../../forgejo/locked-toolchain.nix { };
  rules = "1111111111111111111111111111111111111111";
  validator = locked.writeShellScriptBin "mrjam-validate" "exit 2 # INERT HOST COMPOSITION FIXTURE";
  proposal = { sha256 = lib.concatStrings (lib.replicate 64 "a");
    source = locked.writeTextDir "manifest.json" "INVALID_SYNTHETIC_EVALUATION_ONLY"; };
  publicFixture = builtins.fromJSON (builtins.readFile policyFile);
  authorityPolicy = builtins.removeAttrs (publicFixture // {
    rules_revision = rules; verifier = toString validator;
    verifier_nar_hash = "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=";
    closure_sha256 = lib.concatStrings (lib.replicate 64 "0");
    collector_uid = 952; signer_uid = 953; requester_uid = 950;
    accepted_proposals = [ proposal.sha256 ];
  }) [ "producer" ];
  arguments = {
    rulesRevision = rules; controllerRevision = "2222222222222222222222222222222222222222";
    inherit validator authorityPolicy;
    proposals = [ proposal ];
    policyTokenFile = "/run/synthetic-ci/policy";
    registrationTokenFile = "/run/synthetic-ci/registration";
    signingKeyFile = "/var/lib/mrjam-validation-authority/synthetic-key";
  };
  evaluate = extra: (import (nixpkgs + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux";
    modules = [ ../../hosts/mrjam-vps/candidate-unicast.nix ] ++ extra;
  }).config;
  original = evaluate [ ];
  proposed = evaluate [ (import ../host-profile.nix arguments) ];
  check = config: lib.all (a: a.assertion) config.assertions;
  refuses = modules: let attempt = builtins.tryEval (check (evaluate modules));
    in !attempt.success || !attempt.value;
  ciUnits = [ "mrjam-forgejo-policy" "mrjam-forgejo-registration" "mrjam-forgejo-runner"
    "mrjam-validation-worker@" "mrjam-validation-collector@" "mrjam-validation-staging"
    "mrjam-validation-export@" "mrjam-validation-authority" ];
  ciSockets = [ "mrjam-validation-worker" "mrjam-validation-collector"
    "mrjam-validation-export" "mrjam-validation-authority" ];
  identities = { mrjam-forgejo-registration = 949; mrjam-forgejo-runner = 950;
    mrjam-validation-worker = 951; mrjam-validation-collector = 952; mrjam-validation-authority = 953; };
  appUnits = [ "forgejo" "nginx" "postgresql" "kanidm" "phpfpm-nextcloud" "redis-nextcloud"
    "mrjam-rust-blue" "mrjam-rust-green" "mrjam-identity" "mrjam-identity-deletion"
    "mrjam-vision-admission" "mrjam-vision-archive" "mrjam-vision-closure" "mrjam-vision-cycle"
    "mrjam-vision-replay" "vision-embeddings" ];
  existingUnitChanges = lib.filter (name:
    !(builtins.hasAttr name proposed.systemd.units)
    || proposed.systemd.units.${name}.text != original.systemd.units.${name}.text)
    (builtins.attrNames original.systemd.units);
  results = {
    assertionsPass = check proposed;
    observedIdentityNumbersBound = lib.all (name: proposed.users.users.${name}.uid == identities.${name}
      && proposed.users.groups.${name}.gid == identities.${name}) (builtins.attrNames identities);
    separateSocketGroupsBound = proposed.users.groups.mrjam-validation-submitters.gid == 954
      && proposed.users.groups.mrjam-validation-requesters.gid == 955;
    allApplicationUnitBytesUnchanged = lib.all (name:
      proposed.systemd.units."${name}.service".text == original.systemd.units."${name}.service".text) appUnits;
    allApplicationSettingsUnchanged = proposed.services.mrjamForgejoHost.settings == original.services.mrjamForgejoHost.settings;
    noCIImplicitStart = lib.all (name: proposed.systemd.services.${name}.wantedBy == [ ]) ciUnits
      && lib.all (name: proposed.systemd.sockets.${name}.wantedBy == [ ]) ciSockets;
    actionsRemainDisabled = !proposed.services.mrjamForgejoHost.enableBoundedActions;
    policyPlanOnly = proposed.services.mrjamForgejoPolicy.mode == "plan"
      && proposed.services.mrjamForgejoPolicy.reviewedPlan == null;
    contentAuthorityRequired = proposed.services.mrjamValidationCoordinatorAttestation.enable
      && proposed.services.mrjamValidationAuthority.enable;
    existingFirewallUnitExact = proposed.systemd.units."firewall.service".text == original.systemd.units."firewall.service".text;
    existingUnitsOnlyChangeMaintenanceTriggers = existingUnitChanges
      == [ "dbus-broker.service" "systemd-tmpfiles-resetup.service" ]
      && lib.all (name:
        (lib.filter (line: !lib.hasPrefix "X-Restart-Triggers=" line)
          (lib.splitString "\n" original.systemd.units.${name}.text))
          == (lib.filter (line: !lib.hasPrefix "X-Restart-Triggers=" line)
          (lib.splitString "\n" proposed.systemd.units.${name}.text))) existingUnitChanges
      && original.systemd.services.dbus-broker.reloadIfChanged
      && proposed.systemd.services.dbus-broker.reloadIfChanged;
    onlyCIOutputTableAdded = builtins.attrNames proposed.networking.nftables.tables == [ "mrjam-forgejo-coordinator" ]
      && !proposed.networking.nftables.flushRuleset;
    inputFirewallBackendAndPackagePreserved = proposed.networking.firewall.backend == original.networking.firewall.backend
      && proposed.networking.firewall.package == original.networking.firewall.package;
    llmnrDisabledDnsKept = !proposed.services.resolved.settings.Resolve.LLMNR
      && proposed.services.resolved.settings.Resolve == original.services.resolved.settings.Resolve;
    workerSingleJobBound = proposed.systemd.sockets.mrjam-validation-worker.socketConfig.MaxConnections == 1;
    resourceLimitsRetained = proposed.systemd.services."mrjam-validation-worker@".serviceConfig.MemoryMax == "2G"
      && proposed.systemd.services.mrjam-forgejo-runner.serviceConfig.MemoryMax == "512M"
      && proposed.systemd.services."mrjam-validation-collector@".serviceConfig.MemoryMax == "128M"
      && proposed.systemd.services.mrjam-validation-staging.serviceConfig.MemoryMax == "192M";
    historicalOrphanRulesRefused = refuses [ (import ../host-profile.nix (arguments // {
      rulesRevision = "93bd67666a3b4be9657c333931fa25b2359e165b";
    })) ];
    wrongAuthorityUidRefused = refuses [ (import ../host-profile.nix (arguments // {
      authorityPolicy = authorityPolicy // { signer_uid = 959; };
    })) ];
    flushAllRulesRefused = refuses [ (import ../host-profile.nix arguments)
      { networking.nftables.flushRuleset = lib.mkForce true; } ];
    nftInputMigrationRefused = refuses [ (import ../host-profile.nix arguments)
      { networking.firewall.backend = lib.mkForce "nftables"; } ];
    natMigrationRefused = refuses [ (import ../host-profile.nix arguments)
      { networking.nat.enable = true; } ];
  };
in if delta then {
  scope = "Evaluation-only fixture on phi68; no production candidate or policy";
  baseline = toString original.system.build.toplevel;
  addedUnits = lib.subtractLists (builtins.attrNames original.systemd.units) (builtins.attrNames proposed.systemd.units);
  removedUnits = lib.subtractLists (builtins.attrNames proposed.systemd.units) (builtins.attrNames original.systemd.units);
  changedExistingUnits = builtins.listToAttrs (map (name: { inherit name; value = {
    before_sha256 = builtins.hashString "sha256" original.systemd.units.${name}.text;
    after_sha256 = builtins.hashString "sha256" proposed.systemd.units.${name}.text;
  }; }) existingUnitChanges);
  preservedApplicationUnits = builtins.listToAttrs (map (name: { name = name + ".service";
    value = builtins.hashString "sha256" original.systemd.units."${name}.service".text; }) appUnits);
  firewallUnitSha256 = builtins.hashString "sha256" proposed.systemd.units."firewall.service".text;
  nftablesTable = proposed.networking.nftables.tables.mrjam-forgejo-coordinator;
  newKernelModuleBlacklist = lib.subtractLists original.boot.blacklistedKernelModules proposed.boot.blacklistedKernelModules;
  changedEtcEntries = lib.filter (name:
    !(builtins.hasAttr name original.environment.etc)
    || (toString proposed.environment.etc.${name}.source) != (toString original.environment.etc.${name}.source))
    (builtins.attrNames proposed.environment.etc);
  tmpfilesAdded = lib.subtractLists original.systemd.tmpfiles.rules proposed.systemd.tmpfiles.rules;
  tmpfilesRemoved = lib.subtractLists proposed.systemd.tmpfiles.rules original.systemd.tmpfiles.rules;
} else if detail then {
  originalFirewall = original.systemd.units."firewall.service".text;
  proposedFirewall = proposed.systemd.units."firewall.service".text;
  originalFirewallSettings = builtins.removeAttrs original.networking.firewall [ "package" ];
  proposedFirewallSettings = builtins.removeAttrs proposed.networking.firewall [ "package" ];
  proposedStartContext = builtins.getContext proposed.systemd.services.firewall.serviceConfig.ExecStart;
  originalDbus = original.systemd.units."dbus-broker.service".text;
  proposedDbus = proposed.systemd.units."dbus-broker.service".text;
} else { inherit results; all_passed = lib.all (x: x) (builtins.attrValues results); }
