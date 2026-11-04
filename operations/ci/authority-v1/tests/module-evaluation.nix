{ nixpkgs, policyFile, buildPackage ? false }:
let
  host = import nixpkgs { system = "x86_64-linux"; };
  locked = import ../../../forgejo/locked-toolchain.nix {};
  lib = host.lib;
  input = builtins.fromJSON (builtins.readFile policyFile);
  fake = locked.writeShellScriptBin "mrjam-validate" "exit 2 # synthetic inert source";
  policy = builtins.removeAttrs (input // { verifier = toString fake; }) [ "producer" ];
  fixture = {
    system.stateVersion = "26.05";
    boot.loader.grub.enable = false;
    fileSystems."/" = { device = "synthetic"; fsType = "ext4"; };
    networking.nftables.enable = true;
    services.mrjamForgejoPolicy = { enable = true; mode = "plan"; phase = "operate-validation";
      rulesRevision = policy.rules_revision; controllerRevision = "2222222222222222222222222222222222222222";
      tokenFile = "/run/synthetic/policy"; };
    services.mrjamForgejoRunner = { enable = true; rulesRevision = policy.rules_revision;
      coordinatorUid = policy.requester_uid; registrarUid = policy.requester_uid + 1;
      registrationTokenFile = "/run/synthetic/registration"; };
    services.mrjamValidationWorker = { enable = true; rulesRevision = policy.rules_revision; validator = fake; };
    services.mrjamValidationCollector = { enable = true; rulesRevision = policy.rules_revision; };
    users.users.mrjam-validation-collector.uid = policy.collector_uid;
    services.mrjamValidationStaging = { enable = true; proposals = [ {
      sha256 = lib.concatStrings (lib.replicate 64 "a");
      source = locked.writeTextDir "manifest.json" "INVALID_SYNTHETIC_SOURCE";
    } ]; };
  };
  evaluate = additions: (import (nixpkgs + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux";
    modules = [ ../../modules.nix fixture ] ++ additions;
  }).config;
  base = evaluate [];
  disabled = evaluate [ { services.mrjamValidationAuthority.enable = false; } ];
  enabled = evaluate [ { services.mrjamValidationAuthority = {
    enable = true; inherit policy; signingKeyFile = "/var/lib/mrjam-validation-authority/invented-key";
  }; } ];
  rejected = change: builtins.any (x: !x.assertion) (evaluate [ {
    services.mrjamValidationAuthority = { enable = true; policy = policy // change;
      signingKeyFile = "/var/lib/mrjam-validation-authority/invented-key"; };
  } ]).assertions;
  assertions = builtins.all (x: x.assertion) enabled.assertions;
  services = enabled.systemd.services;
  sockets = enabled.systemd.sockets;
  binding = enabled.services.mrjamValidationAuthority.producerBinding;
  oldWorker = base.systemd.services."mrjam-validation-worker@".serviceConfig;
  newWorker = services."mrjam-validation-worker@".serviceConfig;
  oldCollector = base.systemd.services."mrjam-validation-collector@".serviceConfig;
  newCollector = services."mrjam-validation-collector@".serviceConfig;
  results = {
    enabledAssertionsPass = assertions;
    disabledAddsNoServices = builtins.attrNames base.systemd.services == builtins.attrNames disabled.systemd.services;
    disabledLeavesWorkerExact = oldWorker == disabled.systemd.services."mrjam-validation-worker@".serviceConfig;
    disabledLeavesCollectorExact = oldCollector == disabled.systemd.services."mrjam-validation-collector@".serviceConfig;
    workerOnlyEntryChanged = builtins.removeAttrs oldWorker [ "ExecStart" ] == builtins.removeAttrs newWorker [ "ExecStart" ];
    collectorOnlyEntryChanged = builtins.removeAttrs oldCollector [ "ExecStart" ] == builtins.removeAttrs newCollector [ "ExecStart" ];
    newBoundEntries = lib.hasSuffix "/bin/mrjam-validation-bound-worker" newWorker.ExecStart && lib.hasSuffix "/bin/mrjam-validation-bound-collector" newCollector.ExecStart;
    bindingMatchesWorkerPolicy = binding.worker_policy_sha256 == builtins.hashString "sha256" enabled.environment.etc."mrjam-validation-worker/policy.json".text;
    producerMetadataReadonly = enabled.environment.etc."mrjam-validation-authority/producer.json".mode == "0444";
    signerUidDistinct = services.mrjam-validation-authority.serviceConfig.User == "mrjam-validation-authority" && enabled.users.users.mrjam-validation-authority.uid == policy.signer_uid;
    exporterOwnsNoCredential = !(services."mrjam-validation-export@".serviceConfig ? LoadCredential);
    keyOnlyInSigner = services.mrjam-validation-authority.serviceConfig.LoadCredential == [ "signing-key:/var/lib/mrjam-validation-authority/invented-key" ];
    unixSocketsOnly = sockets.mrjam-validation-export.socketConfig.ListenSequentialPacket == "/run/mrjam-validation-authority/export.sock" && sockets.mrjam-validation-authority.socketConfig.ListenSequentialPacket == "/run/mrjam-validation-authority/request.sock";
    fixedCredentialUnit = !sockets.mrjam-validation-authority.socketConfig.Accept && sockets.mrjam-validation-authority.socketConfig.FileDescriptorName == "authority-request";
    noAutomaticActivation = services.mrjam-validation-authority.wantedBy == [] && services."mrjam-validation-export@".wantedBy == [] && sockets.mrjam-validation-authority.wantedBy == [] && sockets.mrjam-validation-export.wantedBy == [];
    workerHasNoCredential = !(newWorker ? LoadCredential);
    collectorHasNoCredential = !(newCollector ? LoadCredential);
    applicationPackagesUnchanged = enabled.services.forgejo.package.drvPath == base.services.forgejo.package.drvPath && enabled.systemd.package.drvPath == base.systemd.package.drvPath;
    signerCollectorCollisionRefused = rejected { signer_uid = policy.collector_uid; };
    signerRegistrarCollisionRefused = rejected { signer_uid = policy.requester_uid + 1; };
    proposalAbsentFromStagingRefused = rejected { accepted_proposals = [ (lib.concatStrings (lib.replicate 64 "0")) ]; };
    signerCannotReadCollectorCache = builtins.elem "-/var/lib/mrjam-validation-collector" services.mrjam-validation-authority.serviceConfig.InaccessiblePaths;
    exporterCannotReadCredentials = builtins.elem "-/run/credentials" services."mrjam-validation-export@".serviceConfig.InaccessiblePaths;
    originalCoordinatorRemainsUnmodified = base.systemd.services.mrjam-forgejo-runner.serviceConfig == services.mrjam-forgejo-runner.serviceConfig;
  };
in if buildPackage then enabled.services.mrjamValidationAuthority.package else {
  inherit results;
  all_passed = builtins.all (x: x) (builtins.attrValues results);
  assertions_failed = map (x: x.message) (builtins.filter (x: !x.assertion) enabled.assertions);
  package = enabled.services.mrjamValidationAuthority.package.outPath;
}
