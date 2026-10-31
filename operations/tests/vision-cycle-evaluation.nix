{ nixpkgs }:
let
  lib = import (nixpkgs + "/lib");
  evaluate = extra: (import (nixpkgs + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux";
    modules = [ ../nixos/mrjam-vision-cycle.nix {
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
    services.mrjamVisionCycle = {
      enable = true;
      artifactStorePath = "/nix/store/00000000000000000000000000000000-synthetic-vision-cycle";
      visionDatabase = "vision_synthetic"; journalDatabase = "journal_synthetic";
      smtpCredentialFile = "/var/lib/mrjam-secrets/synthetic-smtp.json";
      keycloakCredentialFile = "/var/lib/mrjam-secrets/synthetic-keycloak";
    };
  };
  off = evaluate [ ]; enabled = evaluate [ fixture ];
  service = enabled.systemd.services.mrjam-vision-cycle;
  init = enabled.systemd.services.mrjam-vision-cycle-initialize;
  pg = enabled.services.postgresql;
  checks = {
    disabledInert = !off.services.postgresql.enable && !(off.systemd.services ? mrjam-vision-cycle);
    fixtureValid = valid enabled;
    stateVersionPreserved = enabled.system.stateVersion == "26.05";
    privateUser = enabled.users.users.mrjam-vision-cycle.extraGroups == [ ]
      && enabled.users.users.mrjam-vision-cycle.isSystemUser
      && enabled.users.users.mrjam-vision-cycle.hashedPassword == "!";
    noAutomaticStart = service.wantedBy == [ ] && init.wantedBy == [ ] && !(enabled.systemd.timers ? mrjam-vision-cycle);
    explicitInitialization = lib.hasInfix " initialize-state --config " init.serviceConfig.ExecStart
      && lib.hasInfix " run-once --config " service.serviceConfig.ExecStart && service.preStart == "";
    exclusiveInitialization = builtins.elem "mrjam-vision-cycle.service" init.conflicts;
    leastCredentials = service.serviceConfig.LoadCredential == [ "smtp:/var/lib/mrjam-secrets/synthetic-smtp.json" "keycloak:/var/lib/mrjam-secrets/synthetic-keycloak" ]
      && init.serviceConfig.LoadCredential == [ "smtp:/var/lib/mrjam-secrets/synthetic-smtp.json" ];
    privateDurableState = service.serviceConfig.StateDirectoryMode == "0700";
    budgets = service.serviceConfig.MemoryMax == "256M" && service.serviceConfig.TasksMax == 32
      && service.serviceConfig.CPUQuota == "20%" && service.serviceConfig.TimeoutStartSec == 900
      && !(service.serviceConfig ? RuntimeMaxSec);
    noHostCapabilities = service.serviceConfig.CapabilityBoundingSet == "" && service.serviceConfig.NoNewPrivileges;
    fixedPeerRoles = lib.hasInfix ''local "vision_synthetic" "vision_cycle" peer map=mrjam_rust_slots'' pg.authentication
      && lib.hasInfix ''local "journal_synthetic" "vision_journal_writer" peer map=mrjam_rust_slots'' pg.authentication
      && lib.hasInfix "mrjam_rust_slots mrjam-vision-cycle vision_cycle" pg.identMap
      && lib.hasInfix "mrjam_rust_slots mrjam-vision-cycle vision_journal_writer" pg.identMap;
    noDatabaseOrRoleCreation = pg.ensureDatabases == [ ] && pg.ensureUsers == [ ];
    oldHbaPreserved = lib.hasInfix "local all postgres peer\nlocal all all reject\n" pg.authentication;
    privilegedDatabaseRefused = !(valid (evaluate [ fixture { services.mrjamVisionCycle.visionDatabase = lib.mkForce "postgres"; } ]));
    sharedDatabaseRefused = !(valid (evaluate [ fixture { services.mrjamVisionCycle.journalDatabase = lib.mkForce "vision_synthetic"; } ]));
    wrongRoleRefused = !(valid (evaluate [ fixture { services.mrjamPostgresqlAccess.workers.visionCycle.role = lib.mkForce "vision"; } ]));
    traversalRefused = !(valid (evaluate [ fixture { services.mrjamVisionCycle.smtpCredentialFile = lib.mkForce "/var/lib/secrets/.."; } ]));
    otherIdentityRefused = !(valid (evaluate [ fixture { services.postgresql.identMap = lib.mkAfter "mrjam_rust_slots other_user vision_cycle\n"; } ]));
    buildContextRefused = !(valid (evaluate [ fixture ({pkgs,...}: { services.mrjamVisionCycle.artifactStorePath = lib.mkForce "${pkgs.hello}"; }) ]));
  };
in if lib.all (value: value) (builtins.attrValues checks) then checks
else throw "Cycle module checks failed: ${builtins.toJSON (lib.filterAttrs (_: value: !value) checks)}"
