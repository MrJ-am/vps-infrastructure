# Invented bindings only; actual binaries and SQL are qualified in separate VMs.
{ nixpkgs }:
let
  lib = import (nixpkgs + "/lib");
  names = [ "Admission" "Cycle" "Replay" ];
  unitNames = [ "admission" "cycle" "replay" ];
  base = {
    enable = true;
    artifactStorePath = toString nixpkgs;
    visionDatabase = "vision_synthetic";
    identityProtocol = "kanidm-native";
    kanidmCredentialFile = "/var/lib/synthetic/kanidm";
    kanidmCaFile = (toString nixpkgs) + "/synthetic-ca.pem";
    kanidmCaSha256 = lib.concatStrings (lib.replicate 64 "0");
  };
  evaluate = extra: (import (nixpkgs + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux";
    modules = [ ../nixos/mrjam-vision-admission.nix ../nixos/mrjam-vision-cycle.nix
      ../nixos/mrjam-vision-replay.nix {
        system.stateVersion = "26.05";
        fileSystems."/" = { device = "/dev/synthetic"; fsType = "ext4"; };
        boot.loader.grub.enable = false;
        services.postgresql.enable = true;
        services.mrjamVisionAdmission = base // {
          smtpCredentialFile = "/var/lib/synthetic/smtp";
          closureCredentialFile = "/var/lib/synthetic/closure";
          approvalCredentialFile = "/var/lib/synthetic/approval";
        };
        services.mrjamVisionCycle = base // {
          journalDatabase = "journal_synthetic";
          smtpCredentialFile = "/var/lib/synthetic/smtp";
        };
        services.mrjamVisionReplay = base // {
          journalDatabase = "journal_synthetic";
          admissionsCredentialFile = "/var/lib/synthetic/closure";
        };
      } extra ];
  }).config;
  candidate = evaluate { };
  valid = cfg: lib.all (a: a.assertion) cfg.assertions;
  mixed = evaluate { services.mrjamVisionAdmission.keycloakCredentialFile = "/var/lib/synthetic/keycloak"; };
  noCa = evaluate { services.mrjamVisionReplay.kanidmCaFile = lib.mkForce null; };
  noToken = evaluate { services.mrjamVisionCycle.kanidmCredentialFile = lib.mkForce null; };
  checks = {
    nativeCompositionValid = valid candidate;
    mixedIdentityProtocolRefused = !valid mixed;
    absentPublicCaRefused = !valid noCa;
    absentNativeTokenRefused = !valid noToken;
    exactNativeCredentials = lib.all (name: builtins.elem "kanidm:/var/lib/synthetic/kanidm"
      candidate.systemd.services."mrjam-vision-${name}".serviceConfig.LoadCredential) unitNames;
    noLegacyCredentialLoaded = lib.all (name: lib.all (reference: !(lib.hasPrefix "keycloak:" reference))
      candidate.systemd.services."mrjam-vision-${name}".serviceConfig.LoadCredential) unitNames;
    publicCaRootRetained = builtins.elem (builtins.storePath (toString nixpkgs)) candidate.system.extraDependencies;
    noImplicitPromotion = lib.all (name: candidate.systemd.services."mrjam-vision-${name}".wantedBy == [ ]) unitNames;
    noImplicitAdmissionOpening = !candidate.services.mrjamVisionAdmission.admissionsOpen;
    noImplicitTimers = !candidate.services.mrjamVisionCycle.timer.enable && !candidate.services.mrjamVisionReplay.timer.enable;
    noNativeCredentialsDuringInitialization = lib.all (name:
      !(builtins.elem "kanidm:/var/lib/synthetic/kanidm"
        candidate.systemd.services."mrjam-vision-${name}-initialize".serviceConfig.LoadCredential)) [ "admission" "cycle" ];
  };
in assert lib.all (x: x) (builtins.attrValues checks); checks
