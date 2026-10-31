{ nixpkgs }:
let
  lib = import (nixpkgs + "/lib");
  evaluate = extra: (import (nixpkgs + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux";
    modules = [ ../nixos/mrjam-vision-closure.nix {
      system.stateVersion = "26.05"; boot.loader.grub.enable = false;
      fileSystems."/" = { device = "/dev/disk/by-label/synthetic-root"; fsType = "ext4"; };
    } ] ++ extra;
  }).config;
  valid = c: lib.all (entry: entry.assertion) c.assertions;
  fixture = { pkgs, ... }: {
    services.postgresql = { enable = true; package = pkgs.postgresql_17;
      authentication = "local all postgres peer\nlocal all all reject\n";
      identMap = "existing_map existing_user existing_role\n";
    };
    services.mrjamVisionClosure = {
      enable = true;
      artifactStorePath = "/nix/store/00000000000000000000000000000000-synthetic-vision-closure";
      visionDatabase = "vision_synthetic"; journalDatabase = "journal_synthetic";
      admissionsCredentialFile = "/run/keys/synthetic-closure";
    };
  };
  off = evaluate [ ]; enabled = evaluate [ fixture ];
  service = enabled.systemd.services.mrjam-vision-closure;
  pg = enabled.services.postgresql;
  checks = {
    disabledInert = !off.services.postgresql.enable && !(off.systemd.services ? mrjam-vision-closure);
    fixtureValid = valid enabled;
    stateVersionPreserved = enabled.system.stateVersion == "26.05";
    privateUser = enabled.users.users.mrjam-vision-closure.extraGroups == [ ]
      && enabled.users.users.mrjam-vision-closure.isSystemUser
      && enabled.users.users.mrjam-vision-closure.hashedPassword == "!";
    noAutomaticStart = service.wantedBy == [ ] && service.serviceConfig.Restart == "no";
    explicitReadiness = lib.hasInfix " check-local --config " service.serviceConfig.ExecStartPre
      && lib.hasInfix " serve --config " service.serviceConfig.ExecStart;
    credentialsAreReferences = service.serviceConfig.LoadCredential == [ "admissions:/run/keys/synthetic-closure" ];
    noAdditionalState = !(service.serviceConfig ? StateDirectory);
    budgets = service.serviceConfig.MemoryMax == "256M" && service.serviceConfig.TasksMax == 32
      && service.serviceConfig.CPUQuota == "20%" && service.serviceConfig.TimeoutStartSec == 60;
    noHostCapabilities = service.serviceConfig.CapabilityBoundingSet == "" && service.serviceConfig.NoNewPrivileges;
    privateNetwork = service.serviceConfig.RestrictAddressFamilies == [ "AF_UNIX" "AF_INET" ]
      && service.serviceConfig.IPAddressDeny == "any" && service.serviceConfig.IPAddressAllow == "localhost";
    fixedPeerRoles = lib.hasInfix ''local "vision_synthetic" "vision_fermeture" peer map=mrjam_rust_slots'' pg.authentication
      && lib.hasInfix ''local "journal_synthetic" "vision_journal_fermeture" peer map=mrjam_rust_slots'' pg.authentication
      && lib.hasInfix "mrjam_rust_slots mrjam-vision-closure vision_fermeture" pg.identMap
      && lib.hasInfix "mrjam_rust_slots mrjam-vision-closure vision_journal_fermeture" pg.identMap;
    noDatabaseOrRoleCreation = pg.ensureDatabases == [ ] && pg.ensureUsers == [ ];
    oldHbaPreserved = lib.hasInfix "local all postgres peer\nlocal all all reject\n" pg.authentication;
    privilegedDatabaseRefused = !(valid (evaluate [ fixture { services.mrjamVisionClosure.visionDatabase = lib.mkForce "postgres"; } ]));
    sharedDatabaseRefused = !(valid (evaluate [ fixture { services.mrjamVisionClosure.journalDatabase = lib.mkForce "vision_synthetic"; } ]));
    wrongRoleRefused = !(valid (evaluate [ fixture { services.mrjamPostgresqlAccess.workers.visionClosure.role = lib.mkForce "vision"; } ]));
    traversalRefused = !(valid (evaluate [ fixture { services.mrjamVisionClosure.admissionsCredentialFile = lib.mkForce "/var/lib/secrets/.."; } ]));
    otherIdentityRefused = !(valid (evaluate [ fixture { services.postgresql.identMap = lib.mkAfter "mrjam_rust_slots other_user vision_fermeture\n"; } ]));
    buildContextRefused = !(valid (evaluate [ fixture ({pkgs,...}: { services.mrjamVisionClosure.artifactStorePath = lib.mkForce "${pkgs.hello}"; }) ]));
  };
in if lib.all (value: value) (builtins.attrValues checks) then checks
else throw "Closure module checks failed: ${builtins.toJSON (lib.filterAttrs (_: value: !value) checks)}"
