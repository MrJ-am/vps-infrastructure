{ nixpkgs, buildAuthority ? false }:
let
  pkgs = import nixpkgs { system = "x86_64-linux"; };
  locked = import ../../forgejo/locked-toolchain.nix {};
  proposed = import ./bindings.nix { pkgs = locked; };
  policy = builtins.fromJSON (builtins.readFile ./authority-policy.proposed.json);
  config = (import (nixpkgs + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux";
    modules = [ ../modules.nix {
      system.stateVersion = "26.05";
      boot.loader.grub.enable = false;
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
    } ];
  }).config;
  authority = config.services.mrjamValidationAuthority;
  results = {
    assertionsPass = builtins.all (x: x.assertion) config.assertions;
    currentValidatorExact = toString config.services.mrjamValidationWorker.validator == policy.verifier;
    stagedProposalExactlyAdmitted = policy.accepted_proposals == [ proposed.staging.sha256 ];
    sameProposedRules = config.services.mrjamForgejoRunner.rulesRevision == policy.rules_revision
      && config.services.mrjamValidationWorker.rulesRevision == policy.rules_revision
      && config.services.mrjamValidationCollector.rulesRevision == policy.rules_revision
      && proposed.staging.rulesRevision == policy.rules_revision;
    sourceTreeIdentifiersRemainGitSha1 = builtins.all (x: builtins.stringLength x.tree_sha == 40) policy.sources;
    proposalDigestRemainsSha256 = builtins.stringLength proposed.staging.sha256 == 64;
    observedDistinctUids = config.users.users.mrjam-validation-worker.uid == 951
      && config.users.users.mrjam-validation-collector.uid == 952
      && config.users.users.mrjam-validation-authority.uid == 953
      && config.users.users.mrjam-forgejo-runner.uid == 950;
    credentialV2Selected = pkgs.lib.hasSuffix "-mrjam-validation-authority-credentials-2" authority.package.outPath;
    exactPrivateKeyReference = config.systemd.services.mrjam-validation-authority.serviceConfig.LoadCredential
      == [ "signing-key:/var/lib/mrjam-validation-authority/signing-key" ];
    producerBoundToCurrentValidator = authority.producerBinding.verifier == policy.verifier
      && authority.producerBinding.verifier_nar_hash == policy.verifier_nar_hash
      && authority.producerBinding.report_policy_sha256 == policy.report_policy_sha256
      && authority.producerBinding.closure_sha256 == policy.closure_sha256;
    noAutomaticAuthorityStart = config.systemd.services.mrjam-validation-authority.wantedBy == []
      && config.systemd.sockets.mrjam-validation-authority.wantedBy == [];
    noAutomaticStagingStart = config.systemd.services.mrjam-validation-staging.wantedBy == [];
  };
in if buildAuthority then authority.package else {
  inherit results;
  all_passed = builtins.all (x: x) (builtins.attrValues results);
  assertions_failed = map (x: x.message) (builtins.filter (x: !x.assertion) config.assertions);
  authority_package = authority.package.outPath;
  producer = authority.producerBinding;
  scope = "Evaluation with actual proposed code/policy/public-key bindings, synthetic filesystem/controller/token references only; not a deployable host configuration";
}
