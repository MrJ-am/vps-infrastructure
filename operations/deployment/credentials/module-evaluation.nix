{ nixpkgs }:
let
  lib = import (nixpkgs + "/lib");
  evaluate = extra: (import (nixpkgs + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux";
    modules = [ ../../nixos/mrjam-vision-archive.nix {
      system.stateVersion = "26.05";
      boot.loader.grub.enable = false;
      fileSystems."/" = { device = "/dev/disk/by-label/synthetic-root"; fsType = "ext4"; };
      services.postgresql.enable = true;
      services.mrjamVisionArchive = {
        enable = true;
        artifactStorePath = "/nix/store/00000000000000000000000000000000-synthetic-workers";
        journalDatabase = "vision_journal_synthetic";
        smtpCredentialFile = "/var/lib/mrjam-worker-credentials/v1/smtp.json";
        recipientCredentialFile = "/var/lib/mrjam-worker-credentials/v1/recipient";
        configurationCredentialFile = "/var/lib/mrjam-worker-credentials/v1/archive.json";
        initializeConfigurationCredentialFile = "/var/lib/mrjam-worker-credentials/v1/archive-initialize.json";
      };
    } ] ++ extra;
  }).config;
  valid = c: lib.all (entry: entry.assertion) c.assertions;
  good = evaluate [ ];
  archive = good.systemd.services.mrjam-vision-archive;
  initialize = good.systemd.services.mrjam-vision-archive-initialize;
  checks = {
    privateReferencesValid = valid good;
    noPublicAgeValue = good.services.mrjamVisionArchive.ageRecipient == null;
    exactArchiveReference = lib.hasSuffix " --config /run/credentials/mrjam-vision-archive.service/configuration" archive.serviceConfig.ExecStart;
    exactInitializeReference = lib.hasSuffix " --config /run/credentials/mrjam-vision-archive-initialize.service/configuration" initialize.serviceConfig.ExecStart;
    correctArchiveCredential = builtins.elem "configuration:/var/lib/mrjam-worker-credentials/v1/archive.json" archive.serviceConfig.LoadCredential;
    correctInitializeCredential = builtins.elem "configuration:/var/lib/mrjam-worker-credentials/v1/archive-initialize.json" initialize.serviceConfig.LoadCredential;
    noImplicitStart = archive.wantedBy == [ ] && initialize.wantedBy == [ ] && !(good.systemd.timers ? mrjam-vision-archive);
    mixedPublicAndPrivateRefused = !(valid (evaluate [ { services.mrjamVisionArchive.ageRecipient = "age1" + lib.concatStrings (lib.replicate 58 "q"); } ]));
    incompletePrivatePairRefused = !(valid (evaluate [ { services.mrjamVisionArchive.initializeConfigurationCredentialFile = lib.mkForce null; } ]));
    ambiguousReferenceRefused = !(valid (evaluate [ { services.mrjamVisionArchive.configurationCredentialFile = lib.mkForce "/var/lib/../arbitrary"; } ]));
  };
in if lib.all (value: value) (builtins.attrValues checks) then checks
else throw "Private archive configuration checks failed"
