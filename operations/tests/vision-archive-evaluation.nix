{ nixpkgs }:
let
  lib = import (nixpkgs + "/lib");
  evaluate = extra: (import (nixpkgs + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux";
    modules = [ ../nixos/mrjam-vision-archive.nix {
      system.stateVersion = "26.05";
      boot.loader.grub.enable = false;
      fileSystems."/" = { device = "/dev/disk/by-label/synthetic-root"; fsType = "ext4"; };
    } ] ++ extra;
  }).config;
  valid = c: lib.all (entry: entry.assertion) c.assertions;
  fixture = { pkgs, ... }: {
    services.postgresql = { enable = true; package = pkgs.postgresql_17;
      authentication = "local all postgres peer\nlocal all all reject\n";
      identMap = "existing_map existing_user existing_role\n";
    };
    services.mrjamVisionArchive = {
      enable = true;
      artifactStorePath = "/nix/store/00000000000000000000000000000000-synthetic-vision-workers";
      journalDatabase = "vision_journal_synthetic";
      ageRecipient = "age1" + lib.concatStrings (lib.replicate 58 "q");
      smtpCredentialFile = "/var/lib/mrjam-secrets/synthetic-smtp.json";
      recipientCredentialFile = "/var/lib/mrjam-secrets/synthetic-recipient";
    };
  };
  off = evaluate [ ];
  enabled = evaluate [ fixture ];
  service = enabled.systemd.services.mrjam-vision-archive;
  init = enabled.systemd.services.mrjam-vision-archive-initialize;
  pg = enabled.services.postgresql;
  checks = {
    disabledInert = !off.services.postgresql.enable && !(off.systemd.services ? mrjam-vision-archive);
    fixtureValid = valid enabled;
    stateVersionPreserved = enabled.system.stateVersion == "26.05";
    dedicatedUserNoExtraGroups = enabled.users.users.mrjam-vision-archive.extraGroups == [ ]
      && enabled.users.users.mrjam-vision-archive.isSystemUser;
    noAutomaticStart = service.wantedBy == [ ] && init.wantedBy == [ ] && !(enabled.systemd.timers ? mrjam-vision-archive);
    explicitInitialisation = lib.hasInfix " initialize-state --config " init.serviceConfig.ExecStart
      && lib.hasInfix " run-once --config " service.serviceConfig.ExecStart && service.preStart == "";
    credentialsAreReferences = service.serviceConfig.LoadCredential == [
      "smtp:/var/lib/mrjam-secrets/synthetic-smtp.json" "recipient:/var/lib/mrjam-secrets/synthetic-recipient" ];
    noPrivateKeyReference = builtins.length service.serviceConfig.LoadCredential == 2;
    privateDurableState = service.serviceConfig.StateDirectoryMode == "0700";
    limits = service.serviceConfig.MemoryMax == "256M" && service.serviceConfig.TasksMax == 32
      && service.serviceConfig.Type == "oneshot" && service.serviceConfig.TimeoutStartSec == 900
      && !(service.serviceConfig ? RuntimeMaxSec);
    noHostCapabilities = service.serviceConfig.CapabilityBoundingSet == "" && service.serviceConfig.NoNewPrivileges;
    peerOnlyFixedRole = lib.hasPrefix ''local "vision_journal_synthetic" "vision_journal_archiviste" peer map=mrjam_rust_slots'' pg.authentication
      && lib.hasInfix "mrjam_rust_slots mrjam-vision-archive vision_journal_archiviste" pg.identMap;
    noDatabaseOrRoleCreation = pg.ensureDatabases == [ ] && pg.ensureUsers == [ ];
    oldHbaPreserved = lib.hasInfix "local all postgres peer\nlocal all all reject\n" pg.authentication;
    mismatchedDatabaseRefused = !(valid (evaluate [ fixture {
      services.mrjamPostgresqlAccess.workers.visionArchive.database = lib.mkForce "another_database";
    } ]));
    privilegedDatabaseRefused = !(valid (evaluate [ fixture {
      services.mrjamVisionArchive.journalDatabase = lib.mkForce "postgres";
    } ]));
  };
in if lib.all (value: value) (builtins.attrValues checks) then checks
else throw "Archive module checks failed: ${builtins.toJSON (lib.filterAttrs (_: value: !value) checks)}"
