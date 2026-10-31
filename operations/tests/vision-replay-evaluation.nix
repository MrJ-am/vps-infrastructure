{ nixpkgs }:
let
  lib = import (nixpkgs + "/lib");
  evaluate = extra: (import (nixpkgs + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux";
    modules = [ ../nixos/mrjam-vision-replay.nix {
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
    services.mrjamVisionReplay = {
      enable = true;
      artifactStorePath = "/nix/store/00000000000000000000000000000000-synthetic-vision-replay";
      visionDatabase = "vision_synthetic"; journalDatabase = "vision_journal_synthetic";
      keycloakCredentialFile = "/var/lib/mrjam-secrets/synthetic-keycloak";
      admissionsCredentialFile = "/run/keys/synthetic-admissions";
    };
  };
  off = evaluate [ ];
  enabled = evaluate [ fixture ];
  service = enabled.systemd.services.mrjam-vision-replay;
  pg = enabled.services.postgresql;
  checks = {
    disabledInert = !off.services.postgresql.enable && !(off.systemd.services ? mrjam-vision-replay);
    fixtureValid = valid enabled;
    stateVersionPreserved = enabled.system.stateVersion == "26.05";
    privateUser = enabled.users.users.mrjam-vision-replay.extraGroups == [ ]
      && enabled.users.users.mrjam-vision-replay.isSystemUser
      && enabled.users.users.mrjam-vision-replay.hashedPassword == "!";
    noAutomaticStart = service.wantedBy == [ ] && !(enabled.systemd.timers ? mrjam-vision-replay);
    normalReplayOnly = lib.hasInfix "/bin/vision-replay run-once --config " service.serviceConfig.ExecStart
      && service.preStart == "";
    credentialsAreReferences = service.serviceConfig.LoadCredential == [
      "keycloak:/var/lib/mrjam-secrets/synthetic-keycloak" "admissions:/run/keys/synthetic-admissions" ];
    noAdditionalPersistentState = service.serviceConfig.StateDirectory or [ ] == [ ];
    budgets = service.serviceConfig.MemoryMax == "256M" && service.serviceConfig.TasksMax == 32
      && service.serviceConfig.CPUQuota == "20%" && service.serviceConfig.TimeoutStartSec == 900;
    noHostCapabilities = service.serviceConfig.CapabilityBoundingSet == "" && service.serviceConfig.NoNewPrivileges;
    fixedLoopbackNetwork = service.serviceConfig.IPAddressDeny == "any" && service.serviceConfig.IPAddressAllow == "localhost";
    threeExactPeerMappings = lib.all (role: lib.hasInfix "mrjam_rust_slots mrjam-vision-replay ${role}" pg.identMap)
      [ "vision_journal_rejeu" "vision_cycle" "vision_fermeture" ];
    noDatabaseOrRoleCreation = pg.ensureDatabases == [ ] && pg.ensureUsers == [ ];
    oldHbaPreserved = lib.hasInfix "local all postgres peer\nlocal all all reject\n" pg.authentication;
    sharedDatabaseRefused = !(valid (evaluate [ fixture { services.mrjamVisionReplay.journalDatabase = lib.mkForce "vision_synthetic"; } ]));
    privilegedDatabaseRefused = !(valid (evaluate [ fixture { services.mrjamVisionReplay.visionDatabase = lib.mkForce "postgres"; } ]));
    changedRoleRefused = !(valid (evaluate [ fixture { services.mrjamPostgresqlAccess.workers.visionReplayCycle.role = lib.mkForce "other_role"; } ]));
    otherIdentityRefused = !(valid (evaluate [ fixture { services.postgresql.identMap = lib.mkAfter "mrjam_rust_slots foreign_user vision_cycle\n"; } ]));
    traversalRefused = !(valid (evaluate [ fixture { services.mrjamVisionReplay.keycloakCredentialFile = lib.mkForce "/var/lib/../synthetic"; } ]));
    buildContextRefused = !(valid (evaluate [ fixture ({ pkgs, ... }: { services.mrjamVisionReplay.artifactStorePath = lib.mkForce "${pkgs.hello}"; }) ]));
  };
in if lib.all (value: value) (builtins.attrValues checks) then checks
else throw "Replay module checks failed: ${builtins.toJSON (lib.filterAttrs (_: value: !value) checks)}"
