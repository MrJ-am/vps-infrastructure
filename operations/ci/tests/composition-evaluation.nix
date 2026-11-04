# Synthetic evaluation only. These UIDs, revisions and invalid source fixtures
# are not production choices and cannot start successful validation jobs.
{ nixpkgs }:
let
  host = import nixpkgs { system = "x86_64-linux"; };
  lib = host.lib;
  locked = import ../../forgejo/locked-toolchain.nix { };
  modules = ../modules.nix;
  variant = ../forgejo-host-actions.nix;
  originals = [
    ../../nixos/mrjam-forgejo-policy.nix
    ../../nixos/mrjam-forgejo-runner.nix
    ../../nixos/mrjam-validation-worker.nix
    ../../nixos/mrjam-validation-collector.nix
    ../../nixos/mrjam-validation-staging.nix
  ];
  evaluate = extra: (import (nixpkgs + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux";
    modules = [ {
      system.stateVersion = "26.05";
      boot.loader.grub.enable = false;
      fileSystems."/" = { device = "/dev/disk/by-label/synthetic-ci-root"; fsType = "ext4"; };
    } ] ++ extra;
  }).config;
  rules = "1111111111111111111111111111111111111111";
  validator = locked.writeShellScriptBin "mrjam-validate" "exit 2 # INERT EVALUATION FIXTURE";
  proposal = { sha256 = lib.concatStrings (lib.replicate 64 "a");
    source = locked.writeTextDir "manifest.json" "INVALID_SYNTHETIC_EVALUATION_ONLY"; };
  fixture = {
    networking.nftables.enable = true;
    services.mrjamForgejoPolicy = { enable = true; mode = "plan"; phase = "operate-validation";
      rulesRevision = rules; controllerRevision = "2222222222222222222222222222222222222222";
      tokenFile = "/run/synthetic-ci/policy"; };
    services.mrjamForgejoRunner = { enable = true; rulesRevision = rules;
      coordinatorUid = 61230; registrarUid = 61231; registrationTokenFile = "/run/synthetic-ci/registration"; };
    services.mrjamValidationWorker = { enable = true; rulesRevision = rules; inherit validator; };
    services.mrjamValidationCollector = { enable = true; rulesRevision = rules; };
    services.mrjamValidationStaging = { enable = true; proposals = [ proposal ]; };
  };
  hostFixture = {
    services.postgresql = { enable = true; package = host.postgresql_17; };
    services.mrjamForgejoHost = { enable = true; uid = 977; gid = 977;
      artifactStorePath = builtins.unsafeDiscardStringContext (toString locked.forgejo); };
  };
  plain = evaluate [ ];
  disabled = evaluate [ modules ];
  enabled = evaluate [ modules fixture ];
  duplicate = evaluate ([ modules fixture ] ++ originals);
  importedTwice = evaluate [ modules modules fixture ];
  historical = evaluate [ ../../nixos/mrjam-forgejo-host.nix hostFixture ];
  inactiveVariant = evaluate [ variant hostFixture ];
  activeVariant = evaluate [ variant hostFixture fixture { services.mrjamForgejoHost.enableBoundedActions = true; } ];
  importedWithHistorical = evaluate [ variant ../../nixos/mrjam-forgejo-host.nix hostFixture ];
  poisoned = evaluate [ modules fixture {
    nixpkgs.overlays = [ (_: _: {
      forgejo = throw "HOST_FORGEJO_MUST_NOT_SUPPLY_CI";
      forgejo-runner = throw "HOST_RUNNER_MUST_NOT_SUPPLY_CI";
      bubblewrap = throw "HOST_BUBBLEWRAP_MUST_NOT_SUPPLY_CI";
    }) ];
  } ];
  valid = c: builtins.all (a: a.assertion) c.assertions;
  ciValid = c: builtins.all (a: a.assertion || !(lib.hasPrefix "mrjam" a.message)) c.assertions;
  bad = extra: evaluate [ variant hostFixture fixture { services.mrjamForgejoHost.enableBoundedActions = true; } extra ];
  units = [ "mrjam-forgejo-policy" "mrjam-forgejo-registration" "mrjam-forgejo-runner"
    "mrjam-validation-worker@" "mrjam-validation-collector@" "mrjam-validation-staging" ];
  sockets = [ "mrjam-validation-worker" "mrjam-validation-collector" ];
  workerPolicy = builtins.fromJSON (builtins.unsafeDiscardStringContext enabled.environment.etc."mrjam-validation-worker/policy.json".text);
  originalPinned = path: args@{ config, lib, ... }: import path (args // { pkgs = locked; });
  directPinned = evaluate [
    (originalPinned ../../nixos/mrjam-forgejo-policy.nix)
    (originalPinned ../../nixos/mrjam-forgejo-runner.nix)
    (originalPinned ../../nixos/mrjam-validation-worker.nix)
    (originalPinned ../../nixos/mrjam-validation-collector.nix)
    (args@{ config, lib, ... }: (import ../../nixos/mrjam-validation-staging.nix (args // { pkgs = locked; })) // { imports = [ ]; })
    fixture
  ];
  results = {
    allFiveDisabledByDefault = valid disabled
      && !disabled.services.mrjamForgejoPolicy.enable && !disabled.services.mrjamForgejoRunner.enable
      && !disabled.services.mrjamValidationWorker.enable && !disabled.services.mrjamValidationCollector.enable
      && !disabled.services.mrjamValidationStaging.enable
      && !disabled.services.mrjamValidationAuthority.enable
      && !disabled.services.mrjamValidationCoordinatorAttestation.enable;
    importDoesNotCreateUnits = lib.all (name: !(builtins.hasAttr name disabled.systemd.services)) units
      && lib.all (name: !(builtins.hasAttr name disabled.systemd.sockets)) sockets;
    hostPackagesAndModulesUnchanged = disabled.system.nixos.version == plain.system.nixos.version
      && disabled.services.forgejo.package.drvPath == plain.services.forgejo.package.drvPath
      && disabled.nixpkgs.overlays == [ ] && enabled.nixpkgs.overlays == [ ]
      && enabled.systemd.package.drvPath == plain.systemd.package.drvPath;
    allAssertionsPass = valid enabled && valid activeVariant;
    lockedVersions = locked.forgejo.version == "17.0.1" && locked.forgejo-runner.version == "13.2.0"
      && locked.bubblewrap.version == "0.12.0";
    exactRunnerRecipe = enabled.services.mrjamForgejoRunner.coordinatorPackage.drvPath
      == (locked.callPackage ../../forgejo/runner-admission.nix { }).drvPath;
    exactStagingRecipe = enabled.services.mrjamValidationStaging.package.drvPath
      == (locked.callPackage ../../forgejo/staging-package.nix { }).drvPath;
    workerUsesLockedBubblewrap = workerPolicy.bubblewrap_store == toString locked.bubblewrap;
    workerUsesLockedPython = lib.hasPrefix "${locked.python3}/bin/python3 " enabled.systemd.services."mrjam-validation-worker@".serviceConfig.ExecStart;
    collectorUsesLockedPython = lib.hasPrefix "${locked.python3}/bin/python3 " enabled.systemd.services."mrjam-validation-collector@".serviceConfig.ExecStart;
    policyUsesLockedPython = lib.hasPrefix "${locked.python3}/bin/python3 " enabled.systemd.services.mrjam-forgejo-policy.serviceConfig.ExecStart;
    scopedUnitsEqualDirectQualifiedModules = lib.all (name:
      enabled.systemd.units."${name}.service".text == directPinned.systemd.units."${name}.service".text) units;
    stagingWorkerHasNoDuplicateImport = lib.all (name:
      enabled.systemd.units."${name}.service".text == duplicate.systemd.units."${name}.service".text) units
      && duplicate.systemd.tmpfiles.rules == enabled.systemd.tmpfiles.rules;
    repeatImportHasNoEffect = importedTwice.systemd.tmpfiles.rules == enabled.systemd.tmpfiles.rules;
    hostSubstitutionCannotReplaceCITools = ciValid poisoned
      && poisoned.services.mrjamForgejoRunner.coordinatorPackage.drvPath == enabled.services.mrjamForgejoRunner.coordinatorPackage.drvPath
      && poisoned.services.mrjamValidationStaging.package.drvPath == enabled.services.mrjamValidationStaging.package.drvPath;
    noImplicitStart = lib.all (name: enabled.systemd.services.${name}.wantedBy == [ ]) units
      && lib.all (name: enabled.systemd.sockets.${name}.wantedBy == [ ]) sockets;
    noGenericRunner = enabled.services.gitea-actions-runner.instances == { };
    workerStagingShareExistingLock = builtins.elem "f /run/mrjam-validation-worker/operation.lock 0440 root mrjam-validation-worker -" enabled.systemd.tmpfiles.rules;
    policiesAndCatalogPinSameRules = workerPolicy.rules_revision == rules
      && (builtins.fromJSON enabled.environment.etc."mrjam-forgejo/policy.json".text).rules_revision == rules
      && (builtins.fromJSON (builtins.unsafeDiscardStringContext enabled.environment.etc."mrjam-validation-staging/catalog.json".text)).rules_revision == rules;
    resourcesPreserved = enabled.systemd.services."mrjam-validation-worker@".serviceConfig.MemoryMax == "2G"
      && enabled.systemd.services.mrjam-forgejo-runner.serviceConfig.MemoryMax == "512M"
      && enabled.systemd.services."mrjam-validation-collector@".serviceConfig.MemoryMax == "128M"
      && enabled.systemd.services.mrjam-validation-staging.serviceConfig.MemoryMax == "192M";
    actionsFalseByDefault = !inactiveVariant.services.mrjamForgejoHost.enableBoundedActions
      && !inactiveVariant.services.mrjamForgejoHost.settings.actions.ENABLED;
    inactiveHostVariantByteIdentical = inactiveVariant.systemd.units."forgejo.service".text == historical.systemd.units."forgejo.service".text
      && inactiveVariant.services.mrjamForgejoHost.settings == historical.services.mrjamForgejoHost.settings;
    historicalHostImportReplacedOnce = importedWithHistorical.systemd.units."forgejo.service".text == inactiveVariant.systemd.units."forgejo.service".text;
    actionsRequireExplicitChoice = activeVariant.services.mrjamForgejoHost.settings.actions.ENABLED;
    actionSettingsOnlyDelta = builtins.removeAttrs activeVariant.services.mrjamForgejoHost.settings [ "actions" ]
      == builtins.removeAttrs inactiveVariant.services.mrjamForgejoHost.settings [ "actions" ];
    actionsWithoutRunnerRefused = !ciValid (bad { services.mrjamForgejoRunner.enable = lib.mkForce false; });
    actionsWithoutWorkerRefused = !ciValid (bad { services.mrjamValidationWorker.enable = lib.mkForce false; });
    actionsWithoutCollectorRefused = !ciValid (bad { services.mrjamValidationCollector.enable = lib.mkForce false; });
    actionsWithoutStagingRefused = !ciValid (bad { services.mrjamValidationStaging.enable = lib.mkForce false; });
    actionsWithoutPolicyRefused = !ciValid (bad { services.mrjamForgejoPolicy.enable = lib.mkForce false; });
    bootstrapPhaseRefused = !ciValid (bad { services.mrjamForgejoPolicy.phase = lib.mkForce "bootstrap-repositories"; });
    mismatchedPolicyRulesRefused = !ciValid (bad { services.mrjamForgejoPolicy.rulesRevision = lib.mkForce "3333333333333333333333333333333333333333"; });
    upstreamGenericRunnerRefused = !ciValid (bad { services.gitea-actions-runner.instances.untrusted = { enable = true; url = "http://127.0.0.1:3004"; name = "fixture-only"; tokenFile = "/run/synthetic-ci/forbidden"; labels = [ "synthetic:host" ]; }; });
  };
in assert builtins.all (value: value) (builtins.attrValues results); results
